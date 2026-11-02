"""FFmpeg video edits: original-preserving, cancellable MP4 export."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import select
import subprocess
import tempfile
from library import LibraryError

FILTERS={'Original':'','Vivid':'eq=contrast=1.1:saturation=1.35',
         'Warm':'colorbalance=rs=.08:bs=-.05','Cool':'colorbalance=rs=-.05:bs=.08',
         'Mono':'hue=s=0','Noir':'hue=s=0,eq=contrast=1.3:brightness=-.03'}


class Cancelled(LibraryError):pass


@dataclass(frozen=True)
class Edits:
    start:float
    end:float
    rotation:int=0
    filter:str='Original'
    crop:tuple=(0.,0.,1.,1.)

    def validate(self):
        a,b,c,d=self.crop
        if not all(math.isfinite(value) for value in (self.start,self.end,a,b,c,d)) or not 0<=self.start<self.end:
            raise LibraryError('Choose an end time after the start time.')
        if self.rotation not in (0,90,180,270) or self.filter not in FILTERS:raise LibraryError('Invalid video edit.')
        if not (0<=a<c<=1 and 0<=b<d<=1):raise LibraryError('Choose a valid crop area.')


def probe(uri):
    try:
        result=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',uri],capture_output=True,timeout=40,check=True)
        data=json.loads(result.stdout);video=next(stream for stream in data['streams'] if stream['codec_type']=='video')
        duration=float(data.get('format',{}).get('duration') or video['duration'])
        width,height=int(video['width']),int(video['height'])
        rotation=next((float(side['rotation']) for side in video.get('side_data_list',[]) if 'rotation' in side),0)
        if round(rotation)%180:width,height=height,width
        if not math.isfinite(duration) or duration<=0 or min(width,height)<2:raise ValueError()
        return {'duration':duration,'width':width,'height':height}
    except (OSError,ValueError,KeyError,StopIteration,subprocess.SubprocessError):
        raise LibraryError('Could not read this video. Check that the original is available.') from None


def filters(edits,crop=True,preview=False):
    edits.validate()
    chain=['scale=trunc(iw*sar/2)*2:trunc(ih/2)*2','setsar=1']
    if edits.rotation==90:chain.append('transpose=clock')
    elif edits.rotation==180:chain.extend(['hflip','vflip'])
    elif edits.rotation==270:chain.append('transpose=cclock')
    if crop and edits.crop!=(0.,0.,1.,1.):
        a,b,c,d=edits.crop
        chain.append(f'crop=w=trunc(iw*{c-a:.8f}/2)*2:h=trunc(ih*{d-b:.8f}/2)*2:x=trunc(iw*{a:.8f}/2)*2:y=trunc(ih*{b:.8f}/2)*2')
    if FILTERS[edits.filter]:chain.append(FILTERS[edits.filter])
    if preview:chain.append('scale=w=min(960\\,iw):h=-2')
    return ','.join(chain)


def frame(uri,edits,position=None):
    try:
        result=subprocess.run(['ffmpeg','-nostdin','-v','error','-ss',str(edits.start if position is None else position),'-i',uri,
            '-frames:v','1','-vf',filters(edits,crop=False,preview=True),'-f','image2pipe','-c:v','png','pipe:1'],capture_output=True,timeout=40,check=True)
        if not result.stdout:raise ValueError()
        return result.stdout
    except (OSError,ValueError,subprocess.SubprocessError):raise LibraryError('Could not create the video preview.') from None


def export(uri,destination,edits,cancel,progress=lambda _:None,preview=False,source_path=None):
    edits.validate();destination=Path(destination)
    if destination.suffix.lower()!='.mp4':raise LibraryError('Choose an MP4 filename.')
    if source_path and (destination.resolve()==Path(source_path).resolve() or destination.exists() and os.path.samefile(destination,source_path)):
        raise LibraryError('Save to a different file to preserve the original.')
    if cancel.is_set():raise Cancelled('Export cancelled.')
    temporary=None;process=None
    try:
        fd,name=tempfile.mkstemp(prefix='.galeria-video-',suffix='.mp4',dir=destination.parent);os.close(fd);temporary=Path(name)
        length=min(5,edits.end-edits.start) if preview else edits.end-edits.start
        command=['ffmpeg','-nostdin','-v','error','-y','-ss',str(edits.start),'-i',uri,'-t',str(length),
            '-map','0:v:0','-map','0:a?','-sn','-dn','-vf',filters(edits,preview=preview),
            '-c:v','libx264','-preset','ultrafast' if preview else 'fast','-crf','28' if preview else '20',
            '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-map_metadata','-1','-metadata:s:v:0','rotate=0',
            '-movflags','+faststart','-progress','pipe:1','-nostats',str(temporary)]
        with tempfile.TemporaryFile() as errors:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors,text=True)
            while process.poll() is None:
                if cancel.is_set():raise Cancelled('Export cancelled.')
                if select.select([process.stdout],[],[],.2)[0]:
                    line=process.stdout.readline().strip()
                    if line.startswith('out_time_us='):
                        try:progress(min(.99,max(0,int(line.split('=',1)[1])/1e6/length)))
                        except ValueError:pass
            if cancel.is_set():raise Cancelled('Export cancelled.')
            if process.returncode or not temporary.stat().st_size:raise LibraryError('The video could not be exported. Its format or codec may be unsupported.')
        with temporary.open('rb') as stream:os.fsync(stream.fileno())
        os.replace(temporary,destination);progress(1.)
        return destination
    except OSError as error:
        raise LibraryError('Not enough free space to export this video.' if error.errno==28 else 'Could not save the video in that folder.') from None
    finally:
        if process:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            process.stdout.close()
        if temporary:temporary.unlink(missing_ok=True)
