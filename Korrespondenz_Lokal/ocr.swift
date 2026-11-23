import AppKit
import Foundation
import PDFKit
import ImageIO
import CoreML
import CoreVideo
import Vision

struct Line: Codable {
    let text: String
    let x: Double
    let y: Double
    let height: Double
}

struct Page: Codable {
    let number: Int
    let method: String
    let text: String
    let lines: [Line]
    /// Drehung im Uhrzeigersinn (0, 90, 180, 270), mit der die Seite aufrecht steht.
    var rotation: Int = 0
}

struct Result: Codable {
    let pages: [Page]
    let issues: [Int]
}

enum ReadError: Error { case unreadable, tooManyPages }

func cpuBuffer(_ image: CGImage) throws -> CVPixelBuffer {
    var buffer: CVPixelBuffer?
    let status = CVPixelBufferCreate(kCFAllocatorDefault, image.width, image.height,
                                     kCVPixelFormatType_32BGRA, nil, &buffer)
    guard status == kCVReturnSuccess, let buffer else { throw ReadError.unreadable }
    CVPixelBufferLockBaseAddress(buffer, [])
    defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
    guard let context = CGContext(data: CVPixelBufferGetBaseAddress(buffer),
                                  width: image.width, height: image.height,
                                  bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
                                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo:
                                    CGImageAlphaInfo.premultipliedFirst.rawValue |
                                    CGBitmapInfo.byteOrder32Little.rawValue) else { throw ReadError.unreadable }
    context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
    return buffer
}

func recognize(_ image: CGImage, orientation: CGImagePropertyOrientation = .up) throws -> [Line] {
    try recognizeScored(image, orientation: orientation).lines
}

/// Erkennt den Text und bewertet die Lage: Summe aus Zuversicht × Zeichenzahl und mittlere Zuversicht.
func recognizeScored(_ image: CGImage, orientation: CGImagePropertyOrientation) throws
    -> (lines: [Line], score: Double, confidence: Double) {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["de-DE", "en-US"]
    request.usesLanguageCorrection = true
    do {
        try VNImageRequestHandler(cgImage: image, orientation: orientation).perform([request])
    } catch {
        request.recognitionLevel = .fast
        if #available(macOS 14.0, *) {
            for (stage, devices) in (try? request.supportedComputeStageDevices) ?? [:] {
                if let cpu = devices.first(where: { if case .cpu = $0 { return true }; return false }) {
                    request.setComputeDevice(cpu, for: stage)
                }
            }
        }
        try VNImageRequestHandler(cvPixelBuffer: cpuBuffer(image), orientation: orientation).perform([request])
    }
    var score = 0.0, weights = 0.0
    let lines: [Line] = (request.results ?? []).compactMap { observation in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let letters = Double(candidate.string.filter { $0.isLetter || $0.isNumber }.count)
        score += Double(candidate.confidence) * letters
        weights += letters
        let box = observation.boundingBox
        return Line(text: candidate.string, x: box.minX, y: box.midY, height: box.height)
    }.sorted { left, right in
        let leftRow = (left.y * 125).rounded()
        let rightRow = (right.y * 125).rounded()
        return leftRow == rightRow ? left.x < right.x : leftRow > rightRow
    }
    return (lines, score, weights > 0 ? score / weights : 0)
}

/// Sucht die Lage, in der der Text am besten lesbar ist. Eine aufrechte Seite mit sicher erkanntem Text
/// wird nur einmal gelesen; sonst werden die Lagen „auf dem Kopf“ und „quer“ verglichen.
func recognizeUpright(_ image: CGImage) throws -> (lines: [Line], rotation: Int) {
    let up = try recognizeScored(image, orientation: .up)
    if up.confidence >= 0.8 && up.lines.count >= 3 { return (up.lines, 0) }
    var best = (lines: up.lines, rotation: 0, score: up.score)
    // CGImagePropertyOrientation beschreibt, wie das Bild gedreht werden muss, um aufrecht zu stehen.
    let candidates: [(CGImagePropertyOrientation, Int)] = [(.down, 180), (.right, 90), (.left, 270)]
    for (orientation, rotation) in candidates {
        guard let other = try? recognizeScored(image, orientation: orientation) else { continue }
        if other.score > best.score * 1.3 + 20 { best = (other.lines, rotation, other.score) }
        if rotation == 180 && best.rotation == 180 && other.confidence >= 0.8 { break }
    }
    return (best.lines, best.rotation)
}

/// Schreibt eine aufrecht gedrehte Ansichtsfassung als PDF. Das Original bleibt unverändert.
func writeUprightCopy(_ url: URL, pdf: Bool, rotations: [Int: Int], to output: URL) {
    guard rotations.values.contains(where: { $0 != 0 }) else { return }
    if pdf {
        guard let document = PDFDocument(url: url) else { return }
        for (index, rotation) in rotations where rotation != 0 {
            if let page = document.page(at: index) { page.rotation = (page.rotation + rotation) % 360 }
        }
        document.write(to: output)
        return
    }
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return }
    let document = PDFDocument()
    let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                    kCGImageSourceCreateThumbnailWithTransform: true,
                                    kCGImageSourceThumbnailMaxPixelSize: 3200]
    for index in 0..<CGImageSourceGetCount(source) {
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, index, options as CFDictionary),
              let page = PDFPage(image: NSImage(cgImage: image, size: NSSize(width: image.width, height: image.height)))
        else { continue }
        page.rotation = rotations[index] ?? 0
        document.insert(page, at: document.pageCount)
    }
    if document.pageCount > 0 { document.write(to: output) }
}

func scanPDF(_ url: URL) throws -> Result {
    guard let document = PDFDocument(url: url), !document.isLocked, document.pageCount > 0 else { throw ReadError.unreadable }
    guard document.pageCount <= 40 else { throw ReadError.tooManyPages }
    var pages: [Page] = []
    var issues: [Int] = []
    for index in 0..<document.pageCount {
        guard let page = document.page(at: index) else { issues.append(index + 1); continue }
        let extracted = (page.string ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let digitalLines = extracted.split(whereSeparator: { $0.isNewline }).map { String($0).trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        if digitalLines.count >= 4 && extracted.count >= 100 {
            pages.append(Page(number: index + 1, method: "pdf", text: extracted, lines: digitalLines.map {
                Line(text: $0, x: 0, y: 0, height: 0)
            }))
            continue
        }
        do {
            let bounds = page.bounds(for: .cropBox)
            guard bounds.width > 0, bounds.height > 0 else { throw ReadError.unreadable }
            let scaling = min(2.5, 2500 / max(bounds.width, bounds.height))
            let target = NSSize(width: bounds.width * scaling, height: bounds.height * scaling)
            let thumbnail = page.thumbnail(of: target, for: .cropBox)
            guard let image = thumbnail.cgImage(forProposedRect: nil, context: nil, hints: nil) else { throw ReadError.unreadable }
            let (lines, rotation) = try recognizeUpright(image)
            if !lines.isEmpty {
                pages.append(Page(number: index + 1, method: "ocr", text: lines.map(\.text).joined(separator: "\n"), lines: lines,
                                  rotation: rotation))
            } else if !extracted.isEmpty {
                pages.append(Page(number: index + 1, method: "pdf", text: extracted, lines: digitalLines.map {
                    Line(text: $0, x: 0, y: 0, height: 0)
                }))
            } else {
                issues.append(index + 1)
            }
        } catch {
            if !extracted.isEmpty {
                pages.append(Page(number: index + 1, method: "pdf", text: extracted, lines: digitalLines.map {
                    Line(text: $0, x: 0, y: 0, height: 0)
                }))
            }
            issues.append(index + 1)
        }
    }
    return Result(pages: pages, issues: issues)
}

func scanImage(_ url: URL) throws -> Result {
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { throw ReadError.unreadable }
    let options: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: 3200,
        kCGImageSourceShouldCacheImmediately: true
    ]
    let pageCount = CGImageSourceGetCount(source)
    guard pageCount > 0 else { throw ReadError.unreadable }
    guard pageCount <= 40 else { throw ReadError.tooManyPages }
    var pages: [Page] = []
    var issues: [Int] = []
    for index in 0..<pageCount {
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, index, options as CFDictionary) else {
            issues.append(index + 1)
            continue
        }
        do {
            let (lines, rotation) = try recognizeUpright(image)
            if lines.isEmpty {
                issues.append(index + 1)
            } else {
                pages.append(Page(number: index + 1, method: "ocr", text: lines.map(\.text).joined(separator: "\n"), lines: lines,
                                  rotation: rotation))
            }
        } catch {
            if pageCount == 1 { throw error }
            issues.append(index + 1)
        }
    }
    return Result(pages: pages, issues: issues)
}

do {
    // ocr <pdf|image> <Datei> [Ansichtsfassung.pdf]
    guard [3, 4].contains(CommandLine.arguments.count) else { throw ReadError.unreadable }
    let url = URL(fileURLWithPath: CommandLine.arguments[2])
    let pdf = CommandLine.arguments[1] == "pdf"
    let result = try pdf ? scanPDF(url) : scanImage(url)
    if CommandLine.arguments.count == 4 {
        writeUprightCopy(url, pdf: pdf, rotations: Dictionary(uniqueKeysWithValues: result.pages.map { ($0.number - 1, $0.rotation) }),
                         to: URL(fileURLWithPath: CommandLine.arguments[3]))
    }
    FileHandle.standardOutput.write(try JSONEncoder().encode(result))
} catch {
    FileHandle.standardError.write(Data(String(describing: error).utf8))
    exit(1)
}
