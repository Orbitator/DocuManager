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
    return (request.results ?? []).compactMap { observation in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return Line(text: candidate.string, x: box.minX, y: box.midY, height: box.height)
    }.sorted { left, right in
        let leftRow = (left.y * 125).rounded()
        let rightRow = (right.y * 125).rounded()
        return leftRow == rightRow ? left.x < right.x : leftRow > rightRow
    }
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
            let lines = try recognize(image)
            if !lines.isEmpty {
                pages.append(Page(number: index + 1, method: "ocr", text: lines.map(\.text).joined(separator: "\n"), lines: lines))
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
            let lines = try recognize(image)
            if lines.isEmpty {
                issues.append(index + 1)
            } else {
                pages.append(Page(number: index + 1, method: "ocr", text: lines.map(\.text).joined(separator: "\n"), lines: lines))
            }
        } catch {
            if pageCount == 1 { throw error }
            issues.append(index + 1)
        }
    }
    return Result(pages: pages, issues: issues)
}

do {
    guard CommandLine.arguments.count == 3 else { throw ReadError.unreadable }
    let url = URL(fileURLWithPath: CommandLine.arguments[2])
    let result = try CommandLine.arguments[1] == "pdf" ? scanPDF(url) : scanImage(url)
    FileHandle.standardOutput.write(try JSONEncoder().encode(result))
} catch {
    FileHandle.standardError.write(Data(String(describing: error).utf8))
    exit(1)
}
