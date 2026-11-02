from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from imaging import decode_image
from library import LibraryError
from video_edit import Edits,Cancelled,export,frame,probe


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg runtime required')
class VideoEditTests(unittest.TestCase):
    def test_trim_crop_rotation_filter_audio_and_original_integrity(self):
        with TemporaryDirectory() as root:
            original=Path(root)/'original.mp4';output=Path(root)/'edited.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=12',
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','3','-c:v','libx264',
                '-pix_fmt','yuv420p','-c:a','aac',str(original)],check=True)
            digest=sha256(original.read_bytes()).digest();edits=Edits(.5,2.,90,'Mono',(.1,.2,.9,.8))
            progress=[];export(str(original),output,edits,Event(),progress.append,source_path=original)
            info=probe(str(output));self.assertAlmostEqual(info['duration'],1.5,delta=.12)
            self.assertEqual((info['width'],info['height']),(96,96))
            streams=subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','csv=p=0',str(output)],text=True)
            self.assertIn('audio',streams);self.assertEqual(progress[-1],1.)
            _,_,pixels=decode_image(frame(str(output),Edits(0,info['duration'])))
            self.assertLessEqual(max(abs(pixels[i]-pixels[i+1]) for i in range(0,len(pixels),4)),3)
            self.assertEqual(sha256(original.read_bytes()).digest(),digest)
            with self.assertRaises(LibraryError):export(str(original),original,edits,Event(),source_path=original)
            cancelled=Event();cancelled.set();before=output.read_bytes()
            with self.assertRaises(Cancelled):export(str(original),output,edits,cancelled)
            self.assertEqual(output.read_bytes(),before)
            broken=Path(root)/'broken.mp4';broken.write_bytes(b'not a video')
            with self.assertRaises(LibraryError):export(str(broken),output,edits,Event())
            self.assertEqual(output.read_bytes(),before);self.assertEqual(list(Path(root).glob('.galeria-video-*')),[])

    def test_invalid_edits_are_rejected(self):
        for edits in [Edits(2,1),Edits(float('nan'),2),Edits(0,2,45),Edits(0,2,filter='unknown'),Edits(0,2,crop=(0,0,2,1))]:
            with self.assertRaises(LibraryError):edits.validate()


if __name__=='__main__':unittest.main()
