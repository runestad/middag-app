import base64
import importlib
import io
import json
import unittest
import wave

M = importlib.import_module('api.media_analysis')

class MediaImportTests(unittest.TestCase):
    def audio(self,channels=1,seconds=1):
        output=io.BytesIO()
        with wave.open(output,'wb') as wav:
            wav.setnchannels(channels);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0'*(16000*seconds*channels*2))
        return 'data:audio/wav;base64,'+base64.b64encode(output.getvalue()).decode()

    def test_multipart_audio_has_real_file_and_model(self):
        body,typ=M.audio_body({'audio':self.audio()})
        self.assertIn(b'filename="audio.wav"',body)
        self.assertIn(b'RIFF',body)
        self.assertIn('multipart/form-data; boundary=',typ)

    def test_invalid_audio_and_remote_urls_rejected(self):
        for audio in ['https://example.com/file.wav',self.audio(channels=2),'data:audio/wav;base64,YmFk']:
            with self.assertRaises(ValueError):M.audio_body({'audio':audio})

    def test_frame_limits_and_format(self):
        for frames in [[],[{}]*9,[{'image':'https://example.org/img.jpg'}],[{'image':'data:image/jpeg;base64,YmFk'}]]:
            with self.assertRaises(ValueError):M.frames_body({'frames':frames})

    def test_frames_include_timestamps_and_no_guessing_instruction(self):
        body=json.loads(M.frames_body({'frames':[{'seconds':2,'image':'data:image/jpeg;base64,/9j/AA=='}]}))
        self.assertIn('never infer quantities',body['messages'][0]['content'])
        self.assertIn('2.0',body['messages'][1]['content'][0]['text'])
