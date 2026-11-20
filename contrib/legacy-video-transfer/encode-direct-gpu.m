#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <dlfcn.h>
#import <VideoToolbox/VideoToolbox.h>
#import <CoreVideo/CoreVideo.h>
#import <CoreMedia/CoreMedia.h>
#include <pthread.h>
#include <stdio.h>
typedef struct { FILE *out; int frames; int errors; bool header; bool hevc; pthread_mutex_t lock; } State;
static void nal(FILE *f,const uint8_t *p,size_t n){const uint8_t start[4]={0,0,0,1};fwrite(start,1,4,f);fwrite(p,1,n,f);}
static void encoded(void *ref,void *frame,OSStatus status,VTEncodeInfoFlags flags,CMSampleBufferRef sample){
 State *s=ref;pthread_mutex_lock(&s->lock);
 if(status||!sample||!CMSampleBufferDataIsReady(sample)){s->errors++;pthread_mutex_unlock(&s->lock);return;}
 CMFormatDescriptionRef fmt=CMSampleBufferGetFormatDescription(sample);int nalLength=0;size_t count=0,n=0;const uint8_t *p=NULL;
 OSStatus e=s->hevc?CMVideoFormatDescriptionGetHEVCParameterSetAtIndex(fmt,0,&p,&n,&count,&nalLength):CMVideoFormatDescriptionGetH264ParameterSetAtIndex(fmt,0,&p,&n,&count,&nalLength);
 if(e||nalLength!=4){s->errors++;pthread_mutex_unlock(&s->lock);return;}
 if(!s->header){for(size_t i=0;i<count;i++){
  e=s->hevc?CMVideoFormatDescriptionGetHEVCParameterSetAtIndex(fmt,i,&p,&n,NULL,NULL):CMVideoFormatDescriptionGetH264ParameterSetAtIndex(fmt,i,&p,&n,NULL,NULL);
  if(e){s->errors++;break;}nal(s->out,p,n);
 }s->header=true;}
 CMBlockBufferRef block=CMSampleBufferGetDataBuffer(sample);size_t size=CMBlockBufferGetDataLength(block);uint8_t *data=malloc(size);
 e=CMBlockBufferCopyDataBytes(block,0,size,data);if(e)s->errors++;
 else {size_t at=0;while(at+4<=size){uint32_t len;memcpy(&len,data+at,4);len=CFSwapInt32BigToHost(len);at+=4;if(at+len>size){s->errors++;break;}nal(s->out,data+at,len);at+=len;}}
 free(data);s->frames++;pthread_mutex_unlock(&s->lock);
}
int main(int argc,const char **argv){@autoreleasepool{
 if(argc!=4){fprintf(stderr,"usage: encode_hw h264|hevc output.264|265 source.nv12\n");return 2;}
 BOOL hevc=strcmp(argv[1],"hevc")==0;State state={.out=fopen(argv[2],"wb"),.hevc=hevc};pthread_mutex_init(&state.lock,NULL);FILE *raw=fopen(argv[3],"wb");if(!raw||!state.out)return 3;
 NSDictionary *spec=@{(__bridge NSString*)kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder:@YES};
 NSDictionary *sourceAttrs=@{(__bridge NSString*)kCVPixelBufferPixelFormatTypeKey:@(kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange),(__bridge NSString*)kCVPixelBufferWidthKey:@1920,(__bridge NSString*)kCVPixelBufferHeightKey:@1080,(__bridge NSString*)kCVPixelBufferIOSurfacePropertiesKey:@{}};
 VTCompressionSessionRef session=NULL;OSStatus e=VTCompressionSessionCreate(NULL,1920,1080,hevc?kCMVideoCodecType_HEVC:kCMVideoCodecType_H264,(__bridge CFDictionaryRef)spec,(__bridge CFDictionaryRef)sourceAttrs,NULL,encoded,&state,&session);
 if(e){fprintf(stderr,"FAIL create %s encoder: %d\n",argv[1],(int)e);return 4;}
 if(getenv("REIMS_TRANSFER")){
 NSString *key=[NSString stringWithUTF8String:getenv("REIMS_TRANSFER")];
 NSDictionary *transfer=@{key:@NO};
 OSStatus ts=VTSessionSetProperty(session,kVTCompressionPropertyKey_PixelTransferProperties,(__bridge CFDictionaryRef)transfer);
 printf("Transfer property %s status=%d\n",getenv("REIMS_TRANSFER"),(int)ts);
 }
 VTSessionSetProperty(session,kVTCompressionPropertyKey_RealTime,kCFBooleanTrue);
 VTSessionSetProperty(session,kVTCompressionPropertyKey_AllowFrameReordering,kCFBooleanFalse);
 VTSessionSetProperty(session,kVTCompressionPropertyKey_AverageBitRate,(__bridge CFNumberRef)@6000000);
 VTSessionSetProperty(session,kVTCompressionPropertyKey_ExpectedFrameRate,(__bridge CFNumberRef)@30);
 if((e=VTCompressionSessionPrepareToEncodeFrames(session))){fprintf(stderr,"FAIL prepare: %d\n",(int)e);return 5;}
 CFTypeRef hardware=NULL;e=VTSessionCopyProperty(session,kVTCompressionPropertyKey_UsingHardwareAcceleratedVideoEncoder,NULL,&hardware);
 BOOL hw=!e&&hardware&&CFEqual(hardware,kCFBooleanTrue);if(hardware)CFRelease(hardware);
 printf("Encoder %s hardware=%s\n",argv[1],hw?"true":"false");if(!hw)return 6;
 typedef OSStatus (*CreateMetal)(CFAllocatorRef,id<MTLDevice>,CFTypeRef*);
 typedef OSStatus (*TransferMetal)(CFTypeRef,CVPixelBufferRef,CVPixelBufferRef,void*);
 CreateMetal createMetal=(CreateMetal)dlsym(RTLD_DEFAULT,"VTMetalTransferSessionCreate");
 TransferMetal transferMetal=(TransferMetal)dlsym(RTLD_DEFAULT,"VTMetalTransferSessionTransferImageSync");
 CFTypeRef metal=NULL;if(!createMetal||!transferMetal||createMetal(NULL,MTLCreateSystemDefaultDevice(),&metal))return 9;
 VTSessionSetProperty(metal,CFSTR("ShouldWaitToComplete"),kCFBooleanTrue);
 double gpuSeconds=0;
 for(int i=0;i<60;i++){
  CVPixelBufferRef pb=NULL;NSMutableDictionary *attrs=[@{(__bridge NSString*)kCVPixelBufferIOSurfacePropertiesKey:@{}} mutableCopy]; if(getenv("REIMS_NO_SURFACE"))[attrs removeObjectForKey:(__bridge NSString*)kCVPixelBufferIOSurfacePropertiesKey]; if(getenv("REIMS_ALIGNED")){attrs[(__bridge NSString*)kCVPixelBufferPlaneAlignmentKey]=@64;attrs[(__bridge NSString*)kCVPixelBufferBytesPerRowAlignmentKey]=@64;}
  e=CVPixelBufferCreate(NULL,1920,1080,(getenv("REIMS_BGRA")?kCVPixelFormatType_32BGRA:kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange),(__bridge CFDictionaryRef)attrs,&pb);if(e)return 7;
  CVPixelBufferLockBaseAddress(pb,0);
  if(getenv("REIMS_BGRA")){
   uint8_t *p=CVPixelBufferGetBaseAddress(pb);size_t stride=CVPixelBufferGetBytesPerRow(pb);
   for(int row=0;row<1080;row++){for(int x=0;x<1920;x++){uint8_t v=16+(x+i*3)%220;p[row*stride+x*4]=v;p[row*stride+x*4+1]=getenv("REIMS_COLOR")?16+(row+i*5)%220:v;p[row*stride+x*4+2]=getenv("REIMS_COLOR")?16+(x/2+row/2+i*7)%220:v;p[row*stride+x*4+3]=255;}fwrite(p+row*stride,1,1920*4,raw);}
  }else{
  uint8_t *y=CVPixelBufferGetBaseAddressOfPlane(pb,0),*uv=CVPixelBufferGetBaseAddressOfPlane(pb,1);size_t ys=CVPixelBufferGetBytesPerRowOfPlane(pb,0),us=CVPixelBufferGetBytesPerRowOfPlane(pb,1);
  for(int row=0;row<1080;row++){for(int x=0;x<1920;x++)y[row*ys+x]=16+(x+i*3)%220;fwrite(y+row*ys,1,1920,raw);}
  for(int row=0;row<540;row++){memset(uv+row*us,128,1920);fwrite(uv+row*us,1,1920,raw);}
  }
  CVPixelBufferUnlockBaseAddress(pb,0);
  CVPixelBufferRef converted=NULL;
  NSDictionary *gpuAttrs=@{(__bridge NSString*)kCVPixelBufferIOSurfacePropertiesKey:@{},(__bridge NSString*)kCVPixelBufferPlaneAlignmentKey:@64,(__bridge NSString*)kCVPixelBufferBytesPerRowAlignmentKey:@64};
  if(CVPixelBufferCreate(NULL,1920,1080,kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,(__bridge CFDictionaryRef)gpuAttrs,&converted))return 10;
  if(transferMetal(metal,pb,converted,NULL))return 11;
  CFTypeRef gpuTime=NULL;VTSessionCopyProperty(metal,CFSTR("MostRecentElapsedGPUTime"),NULL,&gpuTime);
  if(gpuTime){double t=0;CFNumberGetValue((CFNumberRef)gpuTime,kCFNumberDoubleType,&t);gpuSeconds+=t;CFRelease(gpuTime);}
  CVPixelBufferRelease(pb);pb=converted;
  // Deliberately no IOSurface/CVPixelBuffer CPU lock of the GPU result.
  e=VTCompressionSessionEncodeFrame(session,pb,CMTimeMake(i,30),CMTimeMake(1,30),NULL,NULL,NULL);CVPixelBufferRelease(pb);
  if(e){fprintf(stderr,"FAIL encode frame %d: %d\n",i,(int)e);state.errors++;break;}
 }
 printf("Direct VTMetal GPU seconds=%f, CPU read locks of output=0\n",gpuSeconds);if(!(gpuSeconds>0))return 12;CFRelease(metal);
 e=VTCompressionSessionCompleteFrames(session,kCMTimeInvalid);VTCompressionSessionInvalidate(session);CFRelease(session);fclose(raw);fclose(state.out);pthread_mutex_destroy(&state.lock);
 printf("%s: codec=%s frames=%d errors=%d completion=%d\n",(e||state.errors||state.frames!=60)?"FAIL":"PASS",argv[1],state.frames,state.errors,(int)e);
 return e||state.errors||state.frames!=60?8:0;
}return 0;}
