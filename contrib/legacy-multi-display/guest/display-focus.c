/* Select the display for macOS's absolute tablet when its host window is entered.
 * Input is a port number and normalized position over an authenticated SSH pipe.
 * No event interception, input capture, or accessibility permission is needed.
 */
#include <ApplicationServices/ApplicationServices.h>
#include <math.h>
#include <stdio.h>

int main(void) {
    unsigned port; double x, y;
    setvbuf(stdout, NULL, _IOLBF, 0);
    puts("READY");
    while (scanf("%u %lf %lf", &port, &x, &y) == 3) {
        CGDirectDisplayID ids[8]; uint32_t n=0;
        if (!isfinite(x) || !isfinite(y) || x<0 || x>1 || y<0 || y>1 ||
            CGGetActiveDisplayList(8, ids, &n) != kCGErrorSuccess) continue;
        for (uint32_t i=0; i<n; i++) {
            if (CGDisplayUnitNumber(ids[i]) != port) continue;
            CGRect b=CGDisplayBounds(ids[i]);
            CGPoint p=CGPointMake(b.origin.x+x*(b.size.width-1),
                                 b.origin.y+y*(b.size.height-1));
            CGError err=CGWarpMouseCursorPosition(p);
            printf("PORT %u STATUS %d AT %.0f %.0f\n",port,err,p.x,p.y);
            break;
        }
    }
    return 0;
}
