#import <AppKit/AppKit.h>
#import <sys/socket.h>
#import <sys/un.h>
#import <unistd.h>

static int connection = -1;
static NSPanel *edgePanel;
static NSWindow *sourcePanel;

static void Send(NSData *bytes) {
    if (connection < 0) {
        return;
    }
    const char *data = bytes.bytes;
    size_t remaining = bytes.length;
    while (remaining > 0) {
        ssize_t count = write(connection, data, remaining);
        if (count <= 0) {
            return;
        }
        data += count;
        remaining -= (size_t)count;
    }
}

static void Report(NSDictionary *message) {
    NSData *json = [NSJSONSerialization dataWithJSONObject:message options:0 error:NULL];
    if (json != nil) {
        fwrite(json.bytes, 1, json.length, stdout);
        fputc('\n', stdout);
        fflush(stdout);
        Send(json);
        Send([NSData dataWithBytes:"\n" length:1]);
    }
}

@interface DragReceiver : NSView
@end

@implementation DragReceiver
- (NSDragOperation)draggingEntered:(id<NSDraggingInfo>)sender {
    NSArray<NSURL *> *urls = [sender.draggingPasteboard readObjectsForClasses:@[NSURL.class]
        options:@{NSPasteboardURLReadingFileURLsOnlyKey: @YES}];
    NSMutableArray<NSString *> *paths = [NSMutableArray array];
    for (NSURL *url in urls) {
        if (url.isFileURL && url.path != nil) {
            [paths addObject:url.path];
        }
    }
    Report(@{@"event": @"enter", @"paths": paths, @"types": sender.draggingPasteboard.types ?: @[]});
    return paths.count == 0 ? NSDragOperationNone : NSDragOperationCopy;
}

- (void)draggingExited:(id<NSDraggingInfo>)sender {
    Report(@{@"event": @"leave"});
}

- (BOOL)performDragOperation:(id<NSDraggingInfo>)sender {
    Report(@{@"event": @"guest-drop"});
    return NO;
}
@end

@interface SourceWindow : NSWindow
@end
@implementation SourceWindow
- (BOOL)canBecomeKeyWindow { return YES; }
@end

@interface DragSource : NSView <NSDraggingSource>
@property(nonatomic, copy) NSArray<NSURL *> *files;
@property(nonatomic, copy) NSNumber *generation;
@property(nonatomic) BOOL began;

@end

@implementation DragSource
- (BOOL)acceptsFirstMouse:(NSEvent *)event {
    return YES;
}

- (void)mouseDown:(NSEvent *)event {
    Report(@{@"event": @"source-press", @"generation": self.generation,
        @"button": @(CGEventSourceButtonState(kCGEventSourceStateCombinedSessionState, kCGMouseButtonLeft))});
    if (self.began) {
        return;
    }
    self.began = YES;
    NSMutableArray<NSDraggingItem *> *items = [NSMutableArray array];
    NSPoint point = [self convertPoint:event.locationInWindow fromView:nil];
    for (NSURL *file in self.files) {
        NSDraggingItem *item = [[NSDraggingItem alloc] initWithPasteboardWriter:file];
        NSRect frame = NSMakeRect(point.x - 18, point.y - 18, 36, 36);
        [item setDraggingFrame:frame contents:[NSWorkspace.sharedWorkspace iconForFile:file.path]];
        [items addObject:item];
    }
    if (items.count == 0) {
        return;
    }
    [self beginDraggingSessionWithItems:items event:event source:self];
    Report(@{@"event": @"source-began", @"generation": self.generation});
}

- (NSDragOperation)draggingSession:(NSDraggingSession *)session
        sourceOperationMaskForDraggingContext:(NSDraggingContext)context {
    return NSDragOperationCopy;
}

- (void)draggingSession:(NSDraggingSession *)session endedAtPoint:(NSPoint)point
        operation:(NSDragOperation)operation {
    [sourcePanel orderOut:nil];
    Report(@{@"event": @"source-done", @"accepted": @((operation & NSDragOperationCopy) != 0),
        @"x": @(point.x), @"y": @(NSMaxY(NSScreen.mainScreen.frame) - point.y),
        @"generation": self.generation});
}
@end

static NSPanel *MakePanel(NSRect bounds) {
    NSPanel *panel = [[NSPanel alloc] initWithContentRect:bounds
        styleMask:NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        backing:NSBackingStoreBuffered defer:NO];
    panel.level = NSFloatingWindowLevel;
    panel.backgroundColor = [NSColor colorWithWhite:0.0 alpha:0.015];
    panel.opaque = NO;
    panel.hasShadow = NO;
    panel.hidesOnDeactivate = NO;
    return panel;
}

static void PrepareSource(NSDictionary *command) {
    NSArray *paths = command[@"files"];
    NSNumber *generation = command[@"generation"];
    NSMutableArray<NSURL *> *files = [NSMutableArray array];
    for (NSString *path in paths) {
        if ([path isKindOfClass:NSString.class] && path.isAbsolutePath &&
            [NSFileManager.defaultManager fileExistsAtPath:path]) {
            [files addObject:[NSURL fileURLWithPath:path]];
        }
    }
    if (files.count == 0 || files.count != paths.count) {
        Report(@{@"event": @"source-done", @"accepted": @NO, @"generation": generation});
        return;
    }
    NSPoint pointer = NSEvent.mouseLocation;
    CGFloat x = pointer.x;
    CGFloat y = pointer.y;
    const CGFloat side = 42;
    NSRect frame = NSMakeRect(x - side / 2, y - side / 2, side, side);
    sourcePanel = [[SourceWindow alloc] initWithContentRect:frame
        styleMask:NSWindowStyleMaskBorderless backing:NSBackingStoreBuffered defer:NO];
    sourcePanel.level = NSFloatingWindowLevel;
    sourcePanel.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces;
    sourcePanel.opaque = YES;
    sourcePanel.backgroundColor = [NSColor colorWithWhite:.2 alpha:1];
    sourcePanel.hasShadow = NO;
    DragSource *view = [[DragSource alloc] initWithFrame:NSMakeRect(0, 0, side, side)];
    view.files = files;
    view.generation = generation;
    sourcePanel.contentView = view;
    [NSApplication.sharedApplication activate];
    [sourcePanel makeKeyAndOrderFront:nil];
    [sourcePanel display];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_MSEC * 120),
        dispatch_get_main_queue(), ^{
            if (sourcePanel.contentView == view && sourcePanel.visible) {
                Report(@{@"event": @"source-ready", @"generation": generation, @"x": @(x), @"y": @(y),
                    @"window": @(sourcePanel.windowNumber),
                    @"underPointer": @([NSWindow windowNumberAtPoint:pointer belowWindowWithWindowNumber:0])});
            }
        });
}

static void Command(NSDictionary *command) {
    if ([command[@"event"] isEqual:@"arm"]) {
        [edgePanel orderFrontRegardless];
    } else if ([command[@"event"] isEqual:@"disarm"]) {
        [edgePanel orderOut:nil];
    } else if ([command[@"event"] isEqual:@"prepare-source"]) {
        PrepareSource(command);
    } else if ([command[@"event"] isEqual:@"hide-source"]) {
        [sourcePanel orderOut:nil];
    }
}

static void Listen(const char *path) {
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof(address.sun_path)) {
        exit(2);
    }
    strlcpy(address.sun_path, path, sizeof(address.sun_path));
    int server = socket(AF_UNIX, SOCK_STREAM, 0);
    if (server < 0 || bind(server, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        listen(server, 1) != 0) {
        perror("file drag socket");
        exit(2);
    }
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INTERACTIVE, 0), ^{
        for (;;) {
            int client = accept(server, NULL, NULL);
            if (client < 0) {
                break;
            }
            int one = 1;
            setsockopt(client, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof(one));
            dispatch_sync(dispatch_get_main_queue(), ^{
                connection = client;
                NSRect screen = NSScreen.mainScreen.frame;
                Report(@{@"event": @"connected", @"width": @(NSWidth(screen)),
                    @"height": @(NSHeight(screen))});
            });
            FILE *reader = fdopen(client, "r");
            if (reader == NULL) {
                close(client);
                continue;
            }
            char *line = NULL;
            size_t capacity = 0;
            ssize_t length;
            while ((length = getline(&line, &capacity, reader)) > 0) {
                @autoreleasepool {
                    NSData *bytes = [NSData dataWithBytes:line length:(NSUInteger)length];
                    id message = [NSJSONSerialization JSONObjectWithData:bytes options:0 error:NULL];
                    if ([message isKindOfClass:NSDictionary.class]) {
                        dispatch_async(dispatch_get_main_queue(), ^{ Command(message); });
                    }
                }
            }
            free(line);
            dispatch_sync(dispatch_get_main_queue(), ^{
                connection = -1;
                [edgePanel orderOut:nil];
                [sourcePanel orderOut:nil];
            });
            fclose(reader);
        }
    });
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 3 || freopen(argv[1], "w", stdout) == NULL) {
            return 1;
        }
        NSApplication *app = NSApplication.sharedApplication;
        [app setActivationPolicy:NSApplicationActivationPolicyAccessory];
        NSRect screen = NSScreen.mainScreen.frame;
        const CGFloat width = 80;
        NSRect edge = NSMakeRect(NSMaxX(screen) - width, NSMinY(screen) + 70,
            width, NSHeight(screen) - 140);
        NSPanel *panel = MakePanel(edge);
        DragReceiver *view = [[DragReceiver alloc] initWithFrame:NSMakeRect(0, 0, NSWidth(edge), NSHeight(edge))];
        [view registerForDraggedTypes:@[NSPasteboardTypeFileURL]];
        panel.contentView = view;
        edgePanel = panel;
        Listen(argv[2]);
        Report(@{@"event": @"ready", @"screen": NSStringFromRect(screen),
            @"edge": NSStringFromRect(edge), @"pid": @(getpid())});
        [app run];
    }
    return 0;
}
