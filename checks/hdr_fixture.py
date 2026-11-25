"""Synthetic CICP images and 10-bit HEVC, without external/private media."""
import struct,zlib,subprocess
from pathlib import Path


def png(path,cicp=(9,16,0,1),size=(64,32),split=False):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    w,h=size
    row=(b'\0'+b'\0'*6*(w//2)+b'\xff'*6*(w-w//2)) if split else b'\0'+struct.pack('>HHH',49152,32768,16384)*w
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,16,2,0,0,0))
    Path(path).write_bytes(data+chunk(b'cICP',bytes(cicp))+chunk(b'IDAT',zlib.compress(row*h))+chunk(b'IEND',b''))
    return Path(path)


def video(path,transfer):
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=15','-t','1',
        '-c:v','libx265','-pix_fmt','yuv420p10le','-threads','1','-x265-params',
        'pools=none:frame-threads=1:log-level=error:colorprim=bt2020:transfer='+transfer+':colormatrix=bt2020nc',str(path)],check=True)
    return Path(path)


def avif(source,path,transfer):
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(source),'-frames:v','1','-c:v','libaom-av1',
        '-still-picture','1','-cpu-used','8','-pix_fmt','yuv444p10le','-color_primaries','bt2020','-color_trc',transfer,
        '-colorspace','bt2020nc',str(path)],check=True)
    return Path(path)
