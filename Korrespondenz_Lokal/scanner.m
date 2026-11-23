#import <Cocoa/Cocoa.h>
#import <Quartz/Quartz.h>
#import <ImageCaptureCore/ImageCaptureCore.h>

@interface ScanWindow : NSObject <NSApplicationDelegate, NSWindowDelegate, ICDeviceBrowserDelegate, IKScannerDeviceViewDelegate>
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) ICDeviceBrowser *browser;
@property(nonatomic, strong) IKScannerDeviceView *scanner;
@property(nonatomic, strong) NSPopUpButton *picker;
@property(nonatomic, strong) NSTextField *status;
@property(nonatomic, strong) NSButton *accept;
@property(nonatomic, strong) NSURL *directory;
@property(nonatomic, strong) NSMutableArray<ICScannerDevice *> *devices;
@property(nonatomic, strong) NSMutableOrderedSet<NSString *> *files;
@end

@implementation ScanWindow

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.devices = [NSMutableArray array];
    self.files = [NSMutableOrderedSet orderedSet];
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

    NSView *content = self.window.contentView;
    for (NSView *view in @[self.picker, self.scanner, self.status, self.accept, cancel]) {
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
        [cancel.centerYAnchor constraintEqualToAnchor:self.accept.centerYAnchor]
    ]];
    self.browser = [[ICDeviceBrowser alloc] init];
    self.browser.delegate = self;
    self.browser.browsedDeviceTypeMask = ICDeviceTypeMaskScanner | ICDeviceLocationTypeMaskLocal | ICDeviceLocationTypeMaskShared;
    [self.browser start];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activate];
}

- (void)refreshDevices {
    ICScannerDevice *selected = self.scanner.scannerDevice;
    if (selected && ![self.devices containsObject:selected]) self.scanner.scannerDevice = nil;
    [self.picker removeAllItems];
    for (ICScannerDevice *device in self.devices) [self.picker addItemWithTitle:device.name ?: @"Scanner"];
    self.picker.enabled = self.devices.count > 0;
    if (self.devices.count == 0) {
        [self.picker addItemWithTitle:@"Kein Scanner gefunden"];
        self.scanner.hidden = YES;
        self.status.stringValue = @"Schalte deinen Scanner ein und prüfe in macOS, ob er als Scanner verfügbar ist.";
        return;
    }
    NSUInteger index = selected ? [self.devices indexOfObject:selected] : NSNotFound;
    [self.picker selectItemAtIndex:(index == NSNotFound ? 0 : (NSInteger)index)];
    [self selectScanner:self.picker];
}

- (void)deviceBrowser:(ICDeviceBrowser *)browser didAddDevice:(ICDevice *)device moreComing:(BOOL)moreComing {
    if ([device isKindOfClass:ICScannerDevice.class]) [self.devices addObject:(ICScannerDevice *)device];
    if (!moreComing) [self refreshDevices];
}

- (void)deviceBrowser:(ICDeviceBrowser *)browser didRemoveDevice:(ICDevice *)device moreGoing:(BOOL)moreGoing {
    if ([device isKindOfClass:ICScannerDevice.class]) [self.devices removeObject:(ICScannerDevice *)device];
    if (!moreGoing) [self refreshDevices];
}

- (void)deviceBrowserDidEnumerateLocalDevices:(ICDeviceBrowser *)browser {
    [self refreshDevices];
}

- (void)selectScanner:(id)sender {
    NSInteger index = self.picker.indexOfSelectedItem;
    if (index < 0 || index >= (NSInteger)self.devices.count) return;
    self.scanner.scannerDevice = self.devices[(NSUInteger)index];
    self.scanner.hidden = NO;
    self.status.stringValue = @"Scanne in PDF, JPEG, PNG oder TIFF. Danach kannst du die Scans übernehmen.";
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
    self.status.stringValue = [NSString stringWithFormat:@"%lu Datei(en) bereit zur Übernahme.", (unsigned long)self.files.count];
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
    [self.browser stop];
}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2) return 1;
        NSApplication *application = NSApplication.sharedApplication;
        [application setActivationPolicy:NSApplicationActivationPolicyRegular];
        ScanWindow *controller = [ScanWindow new];
        controller.directory = [NSURL fileURLWithPath:@(argv[1]) isDirectory:YES];
        application.delegate = controller;
        [application run];
    }
    return 0;
}
