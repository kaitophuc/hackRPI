"""Observe actual hardware cube motion in the isolated task browser."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import time
from check_browser import Browser

SAMPLE = """(() => {
 if(typeof received!=='number'||received<1) return null;
 const c=document.getElementById('frame');
 const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
 let chunks=[];for(let i=0;i<a.length;i+=4096)
   chunks.push(String.fromCharCode.apply(null,a.subarray(i,i+4096)));
 return {rgba:btoa(chunks.join('')),frames:received,width:c.width,height:c.height,
   source:lastStatus.source,scene:lastStatus.scene,angle:lastStatus.angle,
   sequence:lastStatus.sequence,paused:lastStatus.paused,rotation_paused:lastStatus.rotation_paused};
})()"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--debug-port', type=int, default=9225)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output-prefix', default='reports/spinal-rotating-browser')
    args = parser.parse_args()
    browser = Browser(args.debug_port)
    try:
        browser.call('Page.enable')
        browser.call('Runtime.enable')
        browser.call('Page.navigate', dict(url=args.url))
        samples, hashes, angles, sequences = [], set(), set(), set()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            sample = browser.evaluate(SAMPLE)
            if sample is not None:
                rgba = base64.b64decode(sample.pop('rgba'), validate=True)
                if len(rgba) != 320 * 240 * 4 or (sample['width'], sample['height']) != (320, 240):
                    raise RuntimeError('unexpected canvas shape')
                if sample['source'] != 'hardware' or sample['scene'] != 'cube' or sample['paused'] or sample['rotation_paused']:
                    raise RuntimeError('expected running hardware cube: %r' % sample)
                sample['nonblack_pixels'] = sum(bool(rgba[i] | rgba[i+1] | rgba[i+2]) for i in range(0, len(rgba), 4))
                if not 1000 < sample['nonblack_pixels'] < 40000:
                    raise RuntimeError('cube canvas unexpectedly empty or oversized')
                sample['rgba_sha256'] = hashlib.sha256(rgba).hexdigest()
                sample['observed_monotonic'] = time.monotonic()
                hashes.add(sample['rgba_sha256'])
                angles.add(sample['angle'])
                sequences.add(sample['sequence'])
                samples.append(sample)
                if sample['frames'] - samples[0]['frames'] >= 25:
                    break
            time.sleep(.4)
        else:
            raise RuntimeError('did not observe 25 additional displayed hardware frames')
        if min(len(hashes), len(angles), len(sequences)) < 2:
            raise RuntimeError('no changing frame geometry/angle/sequence observed')
        count = samples[-1]['frames'] - samples[0]['frames']
        duration = samples[-1]['observed_monotonic'] - samples[0]['observed_monotonic']
        result = dict(kind='hardware-cube-browser-motion-check', source='hardware',
                      displayed_frames=count, duration_seconds=duration, displayed_fps=count/duration,
                      unique_canvas_hashes=len(hashes), unique_angles=len(angles), samples=samples,
                      scope='motion and hardware source; exact fixed-scene pixels were checked separately')
        png = browser.call('Page.captureScreenshot', dict(format='png', captureBeyondViewport=False))
        Path(args.output_prefix + '.png').write_bytes(base64.b64decode(png['data']))
        Path(args.output_prefix + '.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({key: value for key, value in result.items() if key != 'samples'}))
    finally:
        try:
            browser.call('Browser.close')
        except (EOFError, OSError):
            pass


if __name__ == '__main__':
    main()
