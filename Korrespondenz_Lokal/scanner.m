#import <Cocoa/Cocoa.h>
#import <Quartz/Quartz.h>
#import <ImageCaptureCore/ImageCaptureCore.h>

// Zwei Betriebsarten:
//  direkt  – scannt ohne Dialog mit dem zuletzt benutzten (sonst ersten) Scanner: Einzug wenn vorhanden, sonst Glas,
//            Duplex wenn möglich, 300 dpi Farbe; die Seiten werden zu einem PDF zusammengefügt. Schlägt etwas fehl,
//            öffnet sich automatisch der Dialog.
//  dialog  – Scan-Dialog von macOS (IKScannerDeviceView); nach dem Scannen wird automatisch übernommen.
@interface ScanWindow : NSObject <NSApplicationDelegate, NSWindowDelegate, ICDeviceBrowserDelegate, IKScannerDeviceViewDelegate,
                                  ICScannerDeviceDelegate>
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) ICDeviceBrowser *browser;
@property(nonatomic, strong) IKScannerDeviceView *scanner;
@property(nonatomic, strong) NSPopUpButton *picker;
@property(nonatomic, strong) NSTextField *status;
@property(nonatomic, strong) NSButton *accept;
@property(nonatomic, strong) NSURL *directory;
@property(nonatomic, copy) NSString *hotFolder;
@property(nonatomic, strong) NSMutableArray<ICScannerDevice *> *devices;
@property(nonatomic, strong) NSMutableOrderedSet<NSString *> *files;
@property(nonatomic, copy) NSString *configPath;
@property(nonatomic) BOOL direkt;
@property(nonatomic) BOOL dialogAktiv;
@property(nonatomic) BOOL laeuft;
@property(nonatomic) BOOL fertig;
@property(nonatomic, strong) ICScannerDevice *device;
@property(nonatomic, strong) NSMutableArray<NSURL *> *seiten;
@property(nonatomic, strong) NSPanel *hud;
@property(nonatomic, strong) NSTextField *hudText;
@property(nonatomic) NSUInteger aufloesung;
@property(nonatomic) BOOL duplex;
@end

@implementation ScanWindow

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.devices = [NSMutableArray array];
    self.files = [NSMutableOrderedSet orderedSet];
    self.seiten = [NSMutableArray array];
    self.browser = [[ICDeviceBrowser alloc] init];
    self.browser.delegate = self;
    // Auch Netzwerkscanner (Bonjour/AirScan, die meisten Multifunktionsgeräte im WLAN) und entfernte Geräte suchen.
    self.browser.browsedDeviceTypeMask = (ICDeviceTypeMask)(ICDeviceTypeMaskScanner | ICDeviceLocationTypeMaskLocal |
        ICDeviceLocationTypeMaskShared | ICDeviceLocationTypeMaskBonjour | ICDeviceLocationTypeMaskRemote);
    [self.browser start];
    if (self.direkt) [self startDirekt]; else [self startDialog:nil];
}

// ---------- Direktscan ohne Dialog ----------
- (NSString *)gemerkterScanner {
    NSData *daten = self.configPath ? [NSData dataWithContentsOfFile:self.configPath] : nil;
    NSDictionary *cfg = daten ? [NSJSONSerialization JSONObjectWithData:daten options:0 error:nil] : nil;
    return [cfg isKindOfClass:NSDictionary.class] ? cfg[@"name"] : nil;
}

- (void)scannerMerken:(NSString *)name {
    if (!self.configPath || !name.length) return;
    NSData *daten = [NSJSONSerialization dataWithJSONObject:@{@"name": name} options:0 error:nil];
    [daten writeToFile:self.configPath atomically:YES];
}

- (void)startDirekt {
    self.hud = [[NSPanel alloc] initWithContentRect:NSMakeRect(0, 0, 380, 104)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskUtilityWindow backing:NSBackingStoreBuffered defer:NO];
    self.hud.title = @"Scannen · DocuManager";
    self.hud.level = NSFloatingWindowLevel;
    self.hudText = [NSTextField wrappingLabelWithString:@"Scanner wird gesucht …"];
    NSButton *abbrechen = [NSButton buttonWithTitle:@"Abbrechen" target:self action:@selector(direktAbbrechen:)];
    NSButton *einstellungen = [NSButton buttonWithTitle:@"Einstellungen …" target:self action:@selector(zumDialog:)];
    NSView *inhalt = self.hud.contentView;
    for (NSView *v in @[self.hudText, abbrechen, einstellungen]) { v.translatesAutoresizingMaskIntoConstraints = NO; [inhalt addSubview:v]; }
    [NSLayoutConstraint activateConstraints:@[
        [self.hudText.topAnchor constraintEqualToAnchor:inhalt.topAnchor constant:14],
        [self.hudText.leadingAnchor constraintEqualToAnchor:inhalt.leadingAnchor constant:16],
        [self.hudText.trailingAnchor constraintEqualToAnchor:inhalt.trailingAnchor constant:-16],
        [abbrechen.trailingAnchor constraintEqualToAnchor:inhalt.trailingAnchor constant:-14],
        [abbrechen.bottomAnchor constraintEqualToAnchor:inhalt.bottomAnchor constant:-12],
        [einstellungen.trailingAnchor constraintEqualToAnchor:abbrechen.leadingAnchor constant:-8],
        [einstellungen.centerYAnchor constraintEqualToAnchor:abbrechen.centerYAnchor]]];
    [self.hud center];
    [self.hud makeKeyAndOrderFront:nil];
    [self.hud orderFrontRegardless];
    [NSApp activate];
    // Gemerkten Scanner bevorzugen; nach 4 s den ersten gefundenen nehmen, nach 15 s ohne Scanner zum Dialog.
    [self performSelector:@selector(scannerWaehlen) withObject:nil afterDelay:4];
    [self performSelector:@selector(keinScanner) withObject:nil afterDelay:15];
}

- (void)scannerWaehlen {
    if (!self.direkt || self.device || self.dialogAktiv) return;
    NSString *name = [self gemerkterScanner];
    ICScannerDevice *wahl = nil;
    for (ICScannerDevice *d in self.devices) if (name && [d.name isEqualToString:name]) wahl = d;
    if (!wahl) wahl = self.devices.firstObject;
    if (!wahl) return;
    self.device = wahl;
    self.device.delegate = self;
    self.hudText.stringValue = [NSString stringWithFormat:@"Verbinde mit %@ …", wahl.name ?: @"Scanner"];
    [self.device requestOpenSession];
    [self performSelector:@selector(weiterNachOeffnen) withObject:nil afterDelay:4];
}

- (void)keinScanner {
    if (self.direkt && !self.device && !self.dialogAktiv) [self zumDialogMitGrund:@"Kein Scanner gefunden. Bitte im Dialog wählen."];
}

- (void)device:(ICDevice *)device didOpenSessionWithError:(NSError *)error {
    if (device != self.device || self.dialogAktiv) return;
    if (error) { [self zumDialogMitGrund:[@"Scanner nicht erreichbar: " stringByAppendingString:error.localizedDescription]]; return; }
}

- (void)deviceDidBecomeReady:(ICDevice *)device {
    if (device == self.device && !self.dialogAktiv) [self weiterNachOeffnen];
}

- (void)weiterNachOeffnen {
    if (!self.direkt || self.laeuft || self.dialogAktiv || !self.device) return;
    self.laeuft = YES;
    NSNumber *einzug = @(ICScannerFunctionalUnitTypeDocumentFeeder);
    BOOL hatEinzug = [self.device.availableFunctionalUnitTypes containsObject:einzug];
    ICScannerFunctionalUnitType gewuenscht = hatEinzug ? ICScannerFunctionalUnitTypeDocumentFeeder : ICScannerFunctionalUnitTypeFlatbed;
    if (self.device.selectedFunctionalUnit && self.device.selectedFunctionalUnit.type == gewuenscht) [self einrichtenUndScannen];
    else [self.device requestSelectFunctionalUnit:gewuenscht];
}

- (void)scannerDevice:(ICScannerDevice *)scanner didSelectFunctionalUnit:(ICScannerFunctionalUnit *)functionalUnit error:(NSError *)error {
    if (scanner != self.device || self.dialogAktiv || self.fertig) return;
    if (error) { [self zumDialogMitGrund:error.localizedDescription]; return; }
    [self einrichtenUndScannen];
}

- (void)einrichtenUndScannen {
    ICScannerFunctionalUnit *fu = self.device.selectedFunctionalUnit;
    if (!fu) { [self zumDialogMitGrund:@"Der Scanner meldet keine Scan-Einheit."]; return; }
    // Auflösung: die unterstützte, die 300 dpi am nächsten liegt
    __block NSUInteger beste = fu.resolution, abstand = NSUIntegerMax;
    [fu.supportedResolutions enumerateIndexesUsingBlock:^(NSUInteger r, BOOL *stop) {
        NSUInteger d = r > 300 ? r - 300 : 300 - r;
        if (d < abstand) { abstand = d; beste = r; }
    }];
    fu.resolution = beste;
    self.aufloesung = beste ?: 300;
    fu.pixelDataType = ICScannerPixelDataTypeRGB;
    fu.bitDepth = ICScannerBitDepth8Bits;
    if (fu.type == ICScannerFunctionalUnitTypeDocumentFeeder) {
        ICScannerFunctionalUnitDocumentFeeder *einzug = (ICScannerFunctionalUnitDocumentFeeder *)fu;
        if ([einzug.supportedDocumentTypes containsIndex:ICScannerDocumentTypeA4]) einzug.documentType = ICScannerDocumentTypeA4;
        self.duplex = einzug.supportsDuplexScanning;
        einzug.duplexScanningEnabled = self.duplex;
    } else {
        fu.measurementUnit = ICScannerMeasurementUnitInches;
        NSSize flaeche = fu.physicalSize;
        fu.scanArea = NSMakeRect(0, 0, MIN(8.27, flaeche.width > 0 ? flaeche.width : 8.27), MIN(11.69, flaeche.height > 0 ? flaeche.height : 11.69));
    }
    self.device.transferMode = ICScannerTransferModeFileBased;
    self.device.downloadsDirectory = self.directory;
    self.device.documentName = @"Seite";
    self.device.documentUTI = @"public.jpeg";
    self.hudText.stringValue = [NSString stringWithFormat:@"Scanne mit %@ (%@, %lu dpi%@) …", self.device.name ?: @"Scanner",
        fu.type == ICScannerFunctionalUnitTypeDocumentFeeder ? @"Einzug" : @"Glas", (unsigned long)self.aufloesung,
        self.duplex ? @", beidseitig" : @""];
    [self.device requestScan];
}

- (void)scannerDevice:(ICScannerDevice *)scanner didScanToURL:(NSURL *)url {
    if (scanner != self.device || self.dialogAktiv) return;
    [self.seiten addObject:url];
    self.hudText.stringValue = [NSString stringWithFormat:@"%lu Seite(n) gescannt …", (unsigned long)self.seiten.count];
}

- (void)scannerDevice:(ICScannerDevice *)scanner didCompleteScanWithError:(NSError *)error {
    if (scanner != self.device || self.dialogAktiv || self.fertig) return;
    if (self.seiten.count == 0) {
        [self zumDialogMitGrund:error ? error.localizedDescription : @"Es wurde nichts gescannt. Liegt Papier im Einzug?"];
        return;
    }
    self.fertig = YES;
    self.hudText.stringValue = @"Seiten werden zu einem PDF zusammengefügt …";
    [self scannerMerken:self.device.name];
    [self pdfSchreiben];
}

- (void)pdfSchreiben {
    // Leere Rückseiten (beidseitig gescannt) an der Dateigröße erkennen und auslassen
    NSMutableArray<NSNumber *> *groessen = [NSMutableArray array];
    for (NSURL *u in self.seiten) {
        NSNumber *g = nil; [u getResourceValue:&g forKey:NSURLFileSizeKey error:nil]; [groessen addObject:g ?: @0];
    }
    NSArray *sortiert = [groessen sortedArrayUsingSelector:@selector(compare:)];
    double median = sortiert.count ? [sortiert[sortiert.count / 2] doubleValue] : 0;
    PDFDocument *pdf = [[PDFDocument alloc] init];
    NSRect a4 = NSMakeRect(0, 0, 595, 842);
    for (NSUInteger i = 0; i < self.seiten.count; i++) {
        if (self.duplex && self.seiten.count > 1 && median > 0 && [groessen[i] doubleValue] < median * 0.2) continue;
        NSImage *bild = [[NSImage alloc] initWithContentsOfURL:self.seiten[i]];
        if (!bild) continue;
        NSImageRep *rep = bild.representations.firstObject;
        double b = rep.pixelsWide > 0 ? rep.pixelsWide : bild.size.width, h = rep.pixelsHigh > 0 ? rep.pixelsHigh : bild.size.height;
        NSRect box = b > h ? NSMakeRect(0, 0, 842, 595) : a4;
        PDFPage *seite = [[PDFPage alloc] initWithImage:bild options:@{
            PDFPageImageInitializationOptionMediaBox: [NSValue valueWithRect:box],
            PDFPageImageInitializationOptionCompressionQuality: @0.6}];
        if (seite) [pdf insertPage:seite atIndex:pdf.pageCount];
    }
    NSDateFormatter *f = [[NSDateFormatter alloc] init];
    f.dateFormat = @"yyyy-MM-dd HH.mm";
    NSString *name = [NSString stringWithFormat:@"Scan %@.pdf", [f stringFromDate:[NSDate date]]];
    NSURL *ziel = [self.directory URLByAppendingPathComponent:name];
    if (pdf.pageCount == 0 || ![pdf writeToURL:ziel]) { self.fertig = NO; [self zumDialogMitGrund:@"Das PDF konnte nicht erstellt werden."]; return; }
    for (NSURL *u in self.seiten) [[NSFileManager defaultManager] removeItemAtURL:u error:nil];
    [self.files removeAllObjects];
    [self.files addObject:name];
    [self.device requestCloseSession];
    [self finish:nil];
}

- (void)direktAbbrechen:(id)sender {
    if (self.device && self.laeuft) [self.device requestCancelScan];
    [NSApp terminate:nil];
}

- (void)zumDialog:(id)sender { [self zumDialogMitGrund:nil]; }

- (void)zumDialogMitGrund:(NSString *)grund {
    if (self.dialogAktiv) return;
    if (self.device) { [self.device requestCloseSession]; self.device.delegate = nil; }
    [self.hud orderOut:nil];
    [self startDialog:grund];
}

// ICDeviceDelegate – erforderliche Methoden
- (void)didRemoveDevice:(ICDevice *)device {
    if (device == self.device && !self.fertig && !self.dialogAktiv) [self zumDialogMitGrund:@"Die Verbindung zum Scanner wurde getrennt."];
}
- (void)device:(ICDevice *)device didCloseSessionWithError:(NSError *)error {}
- (void)deviceDidChangeName:(ICDevice *)device {}
- (void)deviceDidChangeSharingState:(ICDevice *)device {}
- (void)device:(ICDevice *)device didReceiveStatusInformation:(NSDictionary *)status {}
- (void)device:(ICDevice *)device didReceiveButtonPress:(NSString *)buttonType {}
- (void)device:(ICDevice *)device didReceiveCustomNotification:(NSDictionary *)notification data:(NSData *)data {}
- (void)scannerDeviceDidBecomeAvailable:(ICScannerDevice *)scanner {}
- (void)scannerDevice:(ICScannerDevice *)scanner didCompleteOverviewScanWithError:(NSError *)error {}
- (void)device:(ICDevice *)device didEncounterError:(NSError *)error {
    if (device == self.device && self.direkt && !self.dialogAktiv && !self.fertig) [self zumDialogMitGrund:error.localizedDescription];
}

// ---------- Scan-Dialog ----------
- (void)startDialog:(NSString *)grund {
    self.dialogAktiv = YES;
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 920, 680)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"Dokument scannen · Korrespondenz";
    self.window.minSize = NSMakeSize(640, 500);
    self.window.delegate = self;
    [self.window center];
    self.picker = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    self.picker.target = self;
    self.picker.action = @selector(selectScanner:);
    [self.picker addItemWithTitle:@"Scanner werden gesucht …"];
    self.picker.enabled = NO;
    self.status = [NSTextField wrappingLabelWithString:
        @"Wähle einen Scanner und scanne in PDF, JPEG, PNG oder TIFF. Bestätige anschließend „Scans übernehmen“."];
    self.accept = [NSButton buttonWithTitle:@"Scans übernehmen" target:self action:@selector(finish:)];
    self.accept.enabled = NO;
    NSButton *cancel = [NSButton buttonWithTitle:@"Abbrechen" target:self action:@selector(cancel:)];
    // Ausweg, falls ein Scanner hier nicht erscheint: „Digitale Bilder“ von macOS oder die Software des Herstellers
    NSButton *capture = [NSButton buttonWithTitle:@"„Digitale Bilder“ öffnen" target:self action:@selector(openImageCapture:)];
    self.scanner = [[IKScannerDeviceView alloc] initWithFrame:NSZeroRect];
    self.scanner.delegate = self;
    self.scanner.hasDisplayModeSimple = YES;
    self.scanner.hasDisplayModeAdvanced = YES;
    self.scanner.mode = IKScannerDeviceViewDisplayModeAdvanced;
    self.scanner.transferMode = IKScannerDeviceViewTransferModeFileBased;
    self.scanner.downloadsDirectory = self.directory;
    self.scanner.displaysDownloadsDirectoryControl = NO;
    self.scanner.displaysPostProcessApplicationControl = NO;
    self.scanner.documentName = @"Scan";
    self.scanner.hidden = YES;
    if (grund.length) self.status.stringValue = grund;

    NSView *content = self.window.contentView;
    for (NSView *view in @[self.picker, self.scanner, self.status, self.accept, cancel, capture]) {
        view.translatesAutoresizingMaskIntoConstraints = NO;
        [content addSubview:view];
    }
    [NSLayoutConstraint activateConstraints:@[
        [self.picker.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:14],
        [self.picker.topAnchor constraintEqualToAnchor:content.topAnchor constant:12],
        [self.scanner.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:8],
        [self.scanner.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-8],
        [self.scanner.topAnchor constraintEqualToAnchor:self.picker.bottomAnchor constant:8],
        [self.status.topAnchor constraintEqualToAnchor:self.scanner.bottomAnchor constant:8],
        [self.status.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:14],
        [self.status.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-14],
        [self.accept.topAnchor constraintEqualToAnchor:self.status.bottomAnchor constant:10],
        [self.accept.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-14],
        [self.accept.bottomAnchor constraintEqualToAnchor:content.bottomAnchor constant:-12],
        [cancel.trailingAnchor constraintEqualToAnchor:self.accept.leadingAnchor constant:-8],
        [cancel.centerYAnchor constraintEqualToAnchor:self.accept.centerYAnchor],
        [capture.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:14],
        [capture.centerYAnchor constraintEqualToAnchor:self.accept.centerYAnchor]
    ]];
    if (self.devices.count) [self refreshDevices];
    // Erscheint nach einiger Zeit kein Scanner, den Ausweg über den Scan-Ordner nennen.
    [self performSelector:@selector(noScannerHint) withObject:nil afterDelay:12];
    // Aus dem Terminal gestartet, holt macOS 14 das Fenster nicht von selbst nach vorne.
    // Deshalb schwebt es über dem Browser und wird ausdrücklich in den Vordergrund gebracht.
    self.window.level = NSFloatingWindowLevel;
    [self.window makeKeyAndOrderFront:nil];
    [self.window orderFrontRegardless];
    [NSApp activate];
    [NSRunningApplication.currentApplication activateWithOptions:NSApplicationActivateAllWindows];
}

- (NSString *)folderHint {
    return self.hotFolder.length
        ? [NSString stringWithFormat:@" Alternativ mit „Digitale Bilder“ oder der Scanner-Software in den Ordner „%@“ scannen; "
           @"Dateien dort kommen automatisch in den Posteingang.", self.hotFolder.lastPathComponent]
        : @"";
}

- (void)noScannerHint {
    if (self.devices.count == 0) {
        self.status.stringValue = [@"Kein Scanner gefunden. Ist er eingeschaltet und im selben Netz? In den Systemeinstellungen "
            @"unter „Drucker & Scanner“ muss er aufgeführt sein." stringByAppendingString:[self folderHint]];
    }
}

- (void)openImageCapture:(id)sender {
    // Scanner freigeben und dieses Fenster schließen, sonst meldet „Digitale Bilder“: „wird von einem anderen
    // Programm verwendet“. DocuManager zeigt danach die Anleitung für „Digitale Bilder“.
    self.scanner.scannerDevice = nil;
    [self.browser stop];
    [[NSData data] writeToURL:[self.directory URLByAppendingPathComponent:@"digitale-bilder"] atomically:YES];
    NSURL *app = [NSWorkspace.sharedWorkspace URLForApplicationWithBundleIdentifier:@"com.apple.Image_Capture"];
    if (app) [NSWorkspace.sharedWorkspace openApplicationAtURL:app configuration:[NSWorkspaceOpenConfiguration configuration]
                                             completionHandler:nil];
    [NSApp performSelector:@selector(terminate:) withObject:nil afterDelay:0.8];
    if (self.hotFolder.length) {
        [[NSFileManager defaultManager] createDirectoryAtPath:self.hotFolder withIntermediateDirectories:YES attributes:nil error:nil];
        self.status.stringValue = [NSString stringWithFormat:@"In „Digitale Bilder“ links den Scanner wählen und bei „Scannen nach“ "
            @"den Ordner „%@“ (in Ihrem Benutzerordner) einstellen. Die Scans erscheinen dann von selbst im Posteingang.",
            self.hotFolder.lastPathComponent];
    }
}

- (void)refreshDevices {
    ICScannerDevice *selected = self.scanner.scannerDevice;
    if (selected && ![self.devices containsObject:selected]) self.scanner.scannerDevice = nil;
    [self.picker removeAllItems];
    for (ICScannerDevice *device in self.devices) [self.picker addItemWithTitle:device.name ?: @"Scanner"];
    self.picker.enabled = self.devices.count > 0;
    if (self.devices.count == 0) {
        [self.picker addItemWithTitle:@"Scanner werden gesucht …"];
        self.scanner.hidden = YES;
        self.status.stringValue = @"Scanner werden gesucht, auch im Netzwerk. Das kann einige Sekunden dauern.";
        return;
    }
    NSUInteger index = selected ? [self.devices indexOfObject:selected] : NSNotFound;
    [self.picker selectItemAtIndex:(index == NSNotFound ? 0 : (NSInteger)index)];
    [self selectScanner:self.picker];
}

- (void)deviceBrowser:(ICDeviceBrowser *)browser didAddDevice:(ICDevice *)device moreComing:(BOOL)moreComing {
    NSLog(@"Gerät gefunden: %@ (Typ %lu)", device.name, (unsigned long)device.type);
    if ([device isKindOfClass:ICScannerDevice.class]) [self.devices addObject:(ICScannerDevice *)device];
    if (self.direkt && !self.dialogAktiv) {  // gemerkten Scanner sofort nehmen
        NSString *name = [self gemerkterScanner];
        if (!self.device && name && [device.name isEqualToString:name]) [self scannerWaehlen];
        return;
    }
    if (!moreComing) [self refreshDevices];
}

- (void)deviceBrowser:(ICDeviceBrowser *)browser didRemoveDevice:(ICDevice *)device moreGoing:(BOOL)moreGoing {
    if ([device isKindOfClass:ICScannerDevice.class]) [self.devices removeObject:(ICScannerDevice *)device];
    if (!moreGoing && self.dialogAktiv) [self refreshDevices];
}

- (void)deviceBrowserDidEnumerateLocalDevices:(ICDeviceBrowser *)browser {
    if (self.dialogAktiv) [self refreshDevices];
}

- (void)selectScanner:(id)sender {
    NSInteger index = self.picker.indexOfSelectedItem;
    if (index < 0 || index >= (NSInteger)self.devices.count) return;
    self.scanner.scannerDevice = self.devices[(NSUInteger)index];
    self.scanner.hidden = NO;
    [self scannerMerken:self.devices[(NSUInteger)index].name];
    self.status.stringValue = @"Scannen Sie in PDF, JPEG, PNG oder TIFF. Der Scan wird danach automatisch übernommen.";
}

- (void)scannerDeviceView:(IKScannerDeviceView *)view didScanToURL:(NSURL *)url fileData:(NSData *)data error:(NSError *)error {
    if (error) {
        self.status.stringValue = error.localizedDescription;
        return;
    }
    if (!url.isFileURL || ![url.URLByDeletingLastPathComponent.URLByResolvingSymlinksInPath.path
        isEqualToString:self.directory.URLByResolvingSymlinksInPath.path]) return;
    NSSet *formats = [NSSet setWithArray:@[@"pdf", @"jpg", @"jpeg", @"png", @"tif", @"tiff"]];
    if (![formats containsObject:url.pathExtension.lowercaseString]) {
        self.status.stringValue = @"Wähle PDF, JPEG, PNG oder TIFF und scanne erneut.";
        return;
    }
    [self.files addObject:url.lastPathComponent];
    self.accept.enabled = YES;
    // Automatisch übernehmen, sobald einige Sekunden keine weitere Datei mehr kommt (mehrere Seiten, Duplex)
    [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(finish:) object:nil];
    [self performSelector:@selector(finish:) withObject:nil afterDelay:4];
    self.status.stringValue = [NSString stringWithFormat:@"%lu Datei(en) gescannt – werden gleich übernommen …", (unsigned long)self.files.count];
}

- (void)scannerDeviceView:(IKScannerDeviceView *)view didEncounterError:(NSError *)error {
    self.status.stringValue = error.localizedDescription;
}

- (void)finish:(id)sender {
    NSError *error = nil;
    NSData *manifest = [NSJSONSerialization dataWithJSONObject:self.files.array options:0 error:&error];
    NSURL *output = [self.directory URLByAppendingPathComponent:@"scan-result.json"];
    if (!manifest || ![manifest writeToURL:output options:NSDataWritingAtomic error:&error]) {
        self.status.stringValue = error.localizedDescription ?: @"Scanliste konnte nicht gespeichert werden.";
        return;
    }
    [NSApp terminate:nil];
}

- (void)cancel:(id)sender { [NSApp terminate:nil]; }
- (void)windowWillClose:(NSNotification *)notification { [NSApp terminate:nil]; }
- (void)applicationWillTerminate:(NSNotification *)notification {
    self.scanner.scannerDevice = nil;
    if (self.device) [self.device requestCloseSession];
    [self.browser stop];
}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc < 2) return 1;
        NSApplication *application = NSApplication.sharedApplication;
        [application setActivationPolicy:NSApplicationActivationPolicyRegular];
        ScanWindow *controller = [ScanWindow new];
        controller.directory = [NSURL fileURLWithPath:@(argv[1]) isDirectory:YES];
        if (argc > 2) controller.hotFolder = @(argv[2]);
        if (argc > 3) controller.configPath = @(argv[3]);
        controller.direkt = argc > 4 && strcmp(argv[4], "direkt") == 0;
        application.delegate = controller;
        [application run];
    }
    return 0;
}
