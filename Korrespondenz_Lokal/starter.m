#import <Cocoa/Cocoa.h>

static NSURL *programURL(void) {
    return [NSBundle.mainBundle.bundleURL.URLByDeletingLastPathComponent URLByAppendingPathComponent:@"app.py"];
}

static NSTask *backend(NSArray<NSString *> *options) {
    NSFileManager *files = NSFileManager.defaultManager;
    NSArray<NSString *> *interpreters = @[
        @"/opt/homebrew/bin/python3", @"/usr/local/bin/python3",
        @"/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
        @"/usr/bin/python3"
    ];
    NSTask *process = [NSTask new];
    for (NSString *interpreter in interpreters) {
        if ([files isExecutableFileAtPath:interpreter]) {
            process.executableURL = [NSURL fileURLWithPath:interpreter];
            break;
        }
    }
    NSURL *script = programURL();
    if (!process.executableURL || ![files isReadableFileAtPath:script.path]) return nil;
    process.currentDirectoryURL = script.URLByDeletingLastPathComponent;
    process.arguments = [@[@"-u", @"-B", script.path] arrayByAddingObjectsFromArray:options];
    return process;
}

@interface AppStarter : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) NSTextField *status;
@property(nonatomic, strong) NSButton *browserButton;
@property(nonatomic, strong) NSTask *server;
@property(nonatomic, strong) NSPipe *output;
@property(nonatomic, strong) NSURL *address;
@property(nonatomic, strong) NSMutableString *log;
@property(nonatomic) BOOL opened;
@end

@implementation AppStarter

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 465, 190)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.releasedWhenClosed = NO;
    self.window.title = @"Korrespondenz";
    self.status = [NSTextField wrappingLabelWithString:@"Die lokale Anwendung wird gestartet …"];
    self.browserButton = [NSButton buttonWithTitle:@"Im Browser öffnen" target:self action:@selector(openBrowser:)];
    self.browserButton.enabled = NO;
    NSStackView *layout = [NSStackView stackViewWithViews:@[self.status, self.browserButton]];
    layout.orientation = NSUserInterfaceLayoutOrientationVertical;
    layout.alignment = NSLayoutAttributeLeading;
    layout.spacing = 14;
    layout.edgeInsets = NSEdgeInsetsMake(20, 20, 20, 20);
    layout.translatesAutoresizingMaskIntoConstraints = NO;
    NSView *content = self.window.contentView;
    [content addSubview:layout];
    [NSLayoutConstraint activateConstraints:@[
        [layout.leadingAnchor constraintEqualToAnchor:content.leadingAnchor],
        [layout.trailingAnchor constraintEqualToAnchor:content.trailingAnchor],
        [layout.topAnchor constraintEqualToAnchor:content.topAnchor],
        [self.status.widthAnchor constraintLessThanOrEqualToConstant:425]
    ]];
    [self.window center];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activate];

    self.address = [NSURL URLWithString:@"http://127.0.0.1:8765"];
    self.log = [NSMutableString string];
    self.server = backend(@[]);
    if (!self.server) {
        self.status.stringValue = @"Python 3 oder app.py fehlt. Lass Korrespondenz.app im Ordner Korrespondenz_Lokal neben app.py.";
        return;
    }

    self.output = [NSPipe pipe];
    self.server.standardOutput = self.output;
    self.server.standardError = self.output;
    __weak AppStarter *weakSelf = self;
    self.output.fileHandleForReading.readabilityHandler = ^(NSFileHandle *handle) {
        NSData *data = handle.availableData;
        if (!data.length) {
            handle.readabilityHandler = nil;
            return;
        }
        NSString *text = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
        if (text) dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf receiveText:text]; });
    };
    self.server.terminationHandler = ^(NSTask *task) {
        dispatch_async(dispatch_get_main_queue(), ^{
            AppStarter *starter = weakSelf;
            if (!starter) return;
            if ([starter.log containsString:@"Address already in use"]) {
                [starter checkExistingServer];
                return;
            }
            starter.browserButton.enabled = NO;
            if (starter.opened) starter.status.stringValue = @"Die lokale Anwendung wurde beendet.";
            else if (!starter.log.length) starter.status.stringValue = @"Die lokale Anwendung konnte nicht gestartet werden.";
        });
    };
    NSError *error = nil;
    if (![self.server launchAndReturnError:&error]) self.status.stringValue = error.localizedDescription;
}

- (void)receiveText:(NSString *)text {
    [self.log appendString:text];
    if (self.log.length > 5000) [self.log deleteCharactersInRange:NSMakeRange(0, self.log.length - 5000)];
    if (!self.opened && [self.log containsString:@"Korrespondenz läuft auf http://127.0.0.1:8765"]) {
        self.status.stringValue = @"Die Anwendung läuft. Lass dieses Fenster geöffnet, solange du sie verwendest.";
        self.opened = YES;
        self.browserButton.enabled = YES;
        [self openBrowser:nil];
    } else if (!self.opened && [self.log containsString:@"konnte http://"]) {
        self.status.stringValue = [self.log stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    }
}

- (void)checkExistingServer {
    NSURL *url = [self.address URLByAppendingPathComponent:@"api/cases"];
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
    request.timeoutInterval = 3;
    [[[NSURLSession sharedSession] dataTaskWithRequest:request completionHandler:
        ^(NSData *data, NSURLResponse *response, NSError *error) {
            id contents = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
            BOOL ownServer = [contents isKindOfClass:NSDictionary.class] &&
                [contents[@"cases"] isKindOfClass:NSArray.class] &&
                [contents[@"statuses"] isKindOfClass:NSArray.class] &&
                [contents[@"groups"] isKindOfClass:NSArray.class];
            dispatch_async(dispatch_get_main_queue(), ^{
                if (ownServer) {
                    self.status.stringValue = @"Die Korrespondenzverwaltung läuft bereits.";
                    self.opened = YES;
                    self.browserButton.enabled = YES;
                    [self openBrowser:nil];
                } else {
                    self.status.stringValue = @"Port 8765 wird bereits verwendet. Beende das andere Programm und starte Korrespondenz erneut.";
                }
            });
        }] resume];
}

- (void)openBrowser:(id)sender {
    if (![NSWorkspace.sharedWorkspace openURL:self.address]) {
        self.status.stringValue = @"Öffne http://127.0.0.1:8765 in deinem Browser.";
    }
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender { return YES; }

- (void)applicationWillTerminate:(NSNotification *)notification {
    if (self.server.running) [self.server interrupt];
}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc == 2 && strcmp(argv[1], "--self-test") == 0) {
            NSTask *test = backend(@[@"--self-test"]);
            if (!test || ![test launchAndReturnError:nil]) return 1;
            [test waitUntilExit];
            return test.terminationStatus;
        }
        NSApplication *application = NSApplication.sharedApplication;
        [application setActivationPolicy:NSApplicationActivationPolicyRegular];
        AppStarter *starter = [AppStarter new];
        application.delegate = starter;
        [application run];
    }
    return 0;
}
