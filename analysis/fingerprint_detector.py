import re
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict


class FingerprintDetector:
    
    def __init__(self):
        self.results = defaultdict(list)
        self.patterns = self._init_patterns()
        
    def _init_patterns(self) -> Dict[str, List[Tuple[str, str]]]:

        patterns = {
            # Canvas Fingerprinting
            'canvas': [
                # Direct API calls
                (r'createImageData|getImageData|toDataURL|toBlob', 'Canvas API call'),
                (r'canvas\.getContext\(["\']2d["\']', 'Canvas 2D context'),
                (r'canvas\.getContext\(["\']webgl["\']|getContext\(["\']experimental-webgl["\']', 'WebGL context'),
                # Characteristic strings for obfuscated code
                (r'data:image/png;base64', 'Base64 encoded canvas data'),
                (r'data:image/webp;base64', 'Base64 WebP canvas data'),
                # Text rendering (often used for fingerprinting)
                (r'fillText|strokeText', 'Canvas text rendering'),
                (r'font\s*=\s*["\'][^"\']*monospace', 'Canvas font setting (monospace)'),
            ],
            
            # WebGL Fingerprinting
            'webgl': [
                (r'getParameter\(.*CONTEXT_LOST|getParameter\(.*RENDERER|getParameter\(.*VENDOR', 'WebGL getParameter calls'),
                (r'gl\.getParameter|webgl\.getParameter', 'WebGL parameter extraction'),
                (r'WEBGL_debug_renderer_info', 'WebGL debug renderer info'),
                (r'UNMASKED_RENDERER|UNMASKED_VENDOR', 'Unmasked WebGL info'),
                (r'getSupportedExtensions|getExtension', 'WebGL extension enumeration'),
            ],
            
            # Font Enumeration
            'fonts': [
                (r'font-family|fontFamily', 'Font family reference'),
                (r'document\.fonts\.check|document\.fonts\.load', 'Font loading API'),
                # Characteristic font lists (like in Metrika)
                (r'monospace.*sans-serif.*serif', 'Font list pattern (monospace first)'),
                (r'sans-serif.*serif.*monospace', 'Font list pattern'),
                (r'measureText|fontMeasurement', 'Text measurement for font detection'),
                # Obfuscated patterns
                (r'["\'][^"\']*monospace[^"\']*["\']\s*;', 'Monospace font string literal'),
            ],
            
            # Audio Context Fingerprinting
            'audio': [
                (r'AudioContext|webkitAudioContext', 'AudioContext API'),
                (r'createOscillator|createAnalyser|createScriptProcessor', 'Audio node creation'),
                (r'oscillatorNode|analyserNode', 'Audio node types'),
                (r'getChannelData|getFloatFrequencyData', 'Audio data extraction'),
                (r'decodeAudioData', 'Audio decoding for fingerprinting'),
            ],
            
            # WebRTC Fingerprinting
            'webrtc': [
                (r'RTCPeerConnection|webkitRTCPeerConnection|mozRTCPeerConnection', 'WebRTC PeerConnection'),
                (r'createOffer|createAnswer', 'WebRTC offer/answer'),
                (r'iceCandidate|onicecandidate', 'WebRTC ICE candidate'),
                (r'localDescription|remoteDescription', 'WebRTC SDP access'),
                (r'getUserMedia|mediaDevices\.getUserMedia', 'Media device access'),
            ],
            
            # Battery API
            'battery': [
                (r'getBattery|navigator\.battery', 'Battery API'),
                (r'battery\.level|battery\.charging', 'Battery status reading'),
            ],
            
            # Navigator Properties
            'navigator': [
                (r'navigator\.userAgent', 'UserAgent access'),
                (r'navigator\.platform', 'Platform detection'),
                (r'navigator\.language|navigator\.languages', 'Language detection'),
                (r'navigator\.hardwareConcurrency', 'CPU core count'),
                (r'navigator\.deviceMemory', 'Device memory'),
                (r'navigator\.connection|navigator\.networkInformation', 'Network info'),
                (r'navigator\.plugins', 'Plugin enumeration'),
                (r'navigator\.mimeTypes', 'MIME type enumeration'),
                (r'screen\.width|screen\.height|screen\.colorDepth', 'Screen properties'),
                (r'screen\.pixelDepth|screen\.availWidth', 'Screen pixel info'),
                (r'timezone|getTimezoneOffset', 'Timezone detection'),
                (r'Intl\.DateTimeFormat.*timeZone', 'Intl timezone API'),
            ],
            
            # Canvas Text Measurement (specific to fingerprinting)
            'canvas_text': [
                (r'measureText\(["\'][^"\']{10,}["\']', 'Long text measurement for fingerprinting'),
                (r'fillText\(["\'][^"\']{20,}["\']', 'Long text rendering'),
            ],
            
            # Hardware/Device APIs
            'hardware': [
                (r'navigator\.maxTouchPoints', 'Touch point detection'),
                (r'navigator\.gpu|navigator\.getGPU', 'GPU API access'),
                (r'devicePixelRatio', 'Device pixel ratio'),
            ],
            
            # Storage/Identifier APIs
            'storage': [
                (r'localStorage|sessionStorage', 'Web Storage API'),
                (r'indexedDB', 'IndexedDB'),
                (r'openDatabase', 'Web SQL'),
                (r'cookiesEnabled|cookieEnabled', 'Cookie check'),
            ],
            
            # Canvas fingerprinting hash functions (characteristic for obfuscated code)
            'hash_functions': [
                # Patterns for finding hash functions in obfuscated code
                (r'0x[0-9a-fA-F]{6,8}\s*\^\s*0x[0-9a-fA-F]{6,8}', 'XOR with hex constants (hashing)'),
                (r'charCodeAt|charAt.*parseInt', 'Character code extraction'),
                (r'\.slice\(.*\).*reduce|reduce\(.*function', 'Array reduction (often for hashing)'),
                (r'btoa|atob', 'Base64 encoding/decoding'),
            ],
            
            # Data Exfiltration / Leaks
            'data_leak': [
                # Network requests with potential data exfiltration
                (r'XMLHttpRequest|ActiveXObject.*XmlHttp', 'XMLHttpRequest (potential data exfiltration)'),
                (r'fetch\s*\(', 'Fetch API (potential data exfiltration)'),
                (r'navigator\.sendBeacon', 'Navigator.sendBeacon (data exfiltration)'),
                (r'new\s+WebSocket\s*\(', 'WebSocket connection (potential data leak)'),
                (r'WebSocket.*send\s*\(', 'WebSocket send (data transmission)'),
                
                # URL construction with sensitive data
                (r'window\.location\s*=\s*.*\+|location\.href\s*=\s*.*\+', 'Dynamic URL assignment (potential data in URL)'),
                (r'window\.open\s*\(.*\+', 'Window.open with concatenated string (potential data leak)'),
                (r'\.src\s*=\s*.*\+', 'Setting src attribute with concatenation (potential data leak)'),
                
                # Cookie manipulation for data exfiltration
                (r'document\.cookie\s*=.*\+', 'Writing to cookie with concatenation'),
                (r'document\.cookie\.indexOf|document\.cookie\.search', 'Reading cookie data'),
                
                # LocalStorage/SessionStorage exfiltration
                (r'localStorage\.setItem.*\+|sessionStorage\.setItem.*\+', 'Storing concatenated data in web storage'),
                (r'localStorage\.getItem.*\+|sessionStorage\.getItem.*\+', 'Retrieving and concatenating storage data'),
                
                # postMessage for cross-frame data leaks
                (r'postMessage\s*\(.*\*\)', 'postMessage to all origins (potential data leak)'),
                (r'postMessage\s*\(.*\+', 'postMessage with concatenated data'),
                
                # Image beacon (common for tracking)
                (r'new\s+Image\s*\(\)\s*;\s*.*\.src\s*=', 'Image beacon creation'),
                (r'img\.src\s*=\s*.*\+', 'Setting image src with data concatenation'),
                
                # Form submission with sensitive data
                (r'form.*submit|form\.submit', 'Form submission (potential data exfiltration)'),
                
                # Canvas data extraction for exfiltration
                (r'toDataURL\s*\(\s*\)\.replace|toDataURL\s*\(\s*\)\.slice', 'Canvas data URL manipulation before exfiltration'),
                
                # Base64 encoded external requests
                (r'atob\s*\(.*\)\s*;\s*.*fetch|atob\s*\(.*\)\s*;\s*.*XMLHttpRequest', 'Decoding base64 before network request'),
                
                # Obfuscated exfiltration patterns
                (r'escape\s*\(.*\)\s*;\s*.*location|encodeURIComponent\s*\(.*\)\s*;\s*.*location', 'Encoding data before URL assignment'),
                (r'\.toString\s*\(\s*36\s*\)', 'Base36 encoding (often used for obfuscation)'),
                (r'\.toString\s*\(\s*16\s*\)', 'Hex encoding (potential data obfuscation)'),
            ],
        }
        
        return patterns
    
    def analyze_file(self, filepath: str) -> Dict[str, any]:
        """
        Analyze a single JavaScript file for fingerprinting signatures.
        
        Args:
            filepath: Path to the file to analyze
            
        Returns:
            Dictionary with analysis results
        """
        results = {
            'file': filepath,
            'size': 0,
            'detections': defaultdict(list),
            'score': 0,
            'is_obfuscated': False,
            'obfuscation_indicators': []
        }
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                results['size'] = len(content)
                
                # Check for obfuscation
                results['is_obfuscated'], results['obfuscation_indicators'] = self._detect_obfuscation(content)
                
                # Search for fingerprinting patterns
                for category, pattern_list in self.patterns.items():
                    for pattern, description in pattern_list:
                        matches = list(re.finditer(pattern, content, re.IGNORECASE))
                        if matches:
                            # Take first 5 matches as samples
                            sample_matches = []
                            for m in matches[:5]:
                                start = max(0, m.start() - 30)
                                end = min(len(content), m.end() + 30)
                                context = content[start:end].replace('\n', ' ').strip()
                                sample_matches.append({
                                    'match': m.group()[:100],
                                    'context': context[:200],
                                    'position': m.start()
                                })
                            
                            results['detections'][category].append({
                                'description': description,
                                'pattern': pattern,
                                'count': len(matches),
                                'samples': sample_matches
                            })
                            results['score'] += len(matches)
                
                # Additional heuristics for obfuscated code
                if results['is_obfuscated']:
                    self._analyze_obfuscated_heuristics(content, results)
                
        except Exception as e:
            results['error'] = str(e)
            
        return results
    
    def _detect_obfuscation(self, content: str) -> Tuple[bool, List[str]]:
        """
        Determine if code is obfuscated.
        
        Returns:
            (is_obfuscated, list_of_indicators)
        """
        indicators = []
        
        # Short variable names (sign of obfuscation)
        short_vars = re.findall(r'\b([a-z_]{1,2})\s*=', content)
        if len(short_vars) > 50:
            indicators.append(f'Many short variable names: {len(short_vars)}')
        
        # Long strings without spaces (base64 or obfuscated code)
        long_strings = re.findall(r'["\']([^"\']{100,})["\']', content)
        if long_strings:
            indicators.append(f'Found long strings: {len(long_strings)}')
        
        # Hex sequences (characteristic of obfuscated code)
        hex_sequences = re.findall(r'\\x[0-9a-fA-F]{2}', content)
        if len(hex_sequences) > 20:
            indicators.append(f'Many hex sequences: {len(hex_sequences)}')
        
        # Unicode escape sequences
        unicode_escapes = re.findall(r'\\u[0-9a-fA-F]{4}', content)
        if len(unicode_escapes) > 10:
            indicators.append(f'Unicode escape sequences: {len(unicode_escapes)}')
        
        # High density of special characters
        special_chars = sum(1 for c in content if c in ';{},[]()!~^&|')
        if len(content) > 0:
            density = special_chars / len(content)
            if density > 0.15:
                indicators.append(f'High special char density: {density:.2%}')
        
        # Check for eval/Function constructor (often in obfuscated code)
        if re.search(r'\beval\s*\(|\bFunction\s*\(|\bsetTimeout\s*\(\s*["\']', content):
            indicators.append('Uses eval/Function constructor')
        
        # Arrays with many numbers (characteristic of encoded strings)
        number_arrays = re.findall(r'\[(\s*\d+\s*,){10,}', content)
        if number_arrays:
            indicators.append(f'Arrays with many numbers: {len(number_arrays)}')
        
        is_obfuscated = len(indicators) >= 2
        return is_obfuscated, indicators
    
    def _analyze_obfuscated_heuristics(self, content: str, results: dict):
        """
        Additional heuristics specifically for obfuscated code.
        """
        
        # Search for patterns characteristic of fingerprinting libraries
        fingerprinting_libs = {
            'FingerprintJS': [r'Fingerprint', r'fpjs', r'visitorId'],
            'ClientJS': [r'ClientJS', r'getFingerprint', r'x64hash128'],
            'Evercookie': [r'evercookie', r'ec_png', r'ec_local'],
            'Yandex Metrika': [r'yaCounter', r'watch\.js', r'Metrika'],
        }
        
        for lib_name, patterns in fingerprinting_libs.items():
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    if 'library_detection' not in results['detections']:
                        results['detections']['library_detection'] = []
                    results['detections']['library_detection'].append({
                        'description': f'Detected library: {lib_name}',
                        'pattern': pattern,
                        'count': 1,
                        'samples': [{'match': pattern, 'context': 'library detection', 'position': 0}]
                    })
                    results['score'] += 10
                    break
        
        # Search for characteristic fingerprinting strings (even in obfuscated form)
        # Look for base64 encoded canvas data patterns
        if re.search(r'data:image/(png|webp);base64,[A-Za-z0-9+/=]{50,}', content):
            if 'canvas' not in results['detections']:
                results['detections']['canvas'] = []
            results['detections']['canvas'].append({
                'description': 'Base64 encoded image data (canvas fingerprinting)',
                'pattern': 'data:image/(png|webp);base64,...',
                'count': 1,
                'samples': []
            })
            results['score'] += 5
        
        # Search for hash functions (simple heuristic)
        hash_indicators = [
            r'function\s+\w+\s*\([^)]*\)\s*{[^}]*for[^{]*\{[^}]*\^[^}]*\}',  # XOR loop
            r'0x[0-9a-f]+\s*\^\s*0x[0-9a-f]+',  # XOR with hex
            r'\.reduce\([^,]+,\s*0x[0-9a-f]+',  # Reduce with initial hex value
        ]
        
        for pattern in hash_indicators:
            if re.search(pattern, content):
                if 'hash_functions' not in results['detections']:
                    results['detections']['hash_functions'] = []
                results['detections']['hash_functions'].append({
                    'description': 'Potential hash function (obfuscated code)',
                    'pattern': pattern[:50],
                    'count': 1,
                    'samples': []
                })
                results['score'] += 3


def analyze_directory(directory: str, output_file: Optional[str] = None) -> List[Dict]:
    """
    Analyze all JavaScript files in a directory.
    
    Args:
        directory: Path to directory with JS files
        output_file: Optional path to save results as JSON
        
    Returns:
        List of analysis results for each file
    """
    detector = FingerprintDetector()
    all_results = []
    
    js_files = list(Path(directory).glob('**/*.js'))
    
    print(f"Found JavaScript files: {len(js_files)}")
    print("=" * 60)
    
    for i, js_file in enumerate(js_files, 1):
        print(f"[{i}/{len(js_files)}] Analyzing: {js_file.name}")
        
        result = detector.analyze_file(str(js_file))
        all_results.append(result)
        
        # Brief report
        if result.get('detections'):
            print(f"  [+] Categories found: {len(result['detections'])}")
            print(f"  [+] Fingerprinting score: {result['score']}")
            if result['is_obfuscated']:
                print(f"  [!] Code is obfuscated")
    
    # Sort by score (most suspicious first)
    all_results.sort(key=lambda x: x['score'], reverse=True)
    
    # Save results
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {output_file}")
    
    return all_results


def print_summary(results: List[Dict]):
    """Print summary statistics of analysis results."""
    
    print("\n" + "=" * 60)
    print("SUMMARY REPORT")
    print("=" * 60)
    
    total_files = len(results)
    files_with_fingerprinting = sum(1 for r in results if r.get('detections'))
    obfuscated_files = sum(1 for r in results if r.get('is_obfuscated'))
    
    print(f"Total files analyzed: {total_files}")
    print(f"Files with fingerprinting signs: {files_with_fingerprinting}")
    print(f"Obfuscated files: {obfuscated_files}")
    
    # Top files by score
    print("\nTOP 10 files with highest fingerprinting score:")
    print("-" * 60)
    for i, r in enumerate(results[:10], 1):
        if r['score'] > 0:
            print(f"{i}. {Path(r['file']).name}")
            print(f"   Score: {r['score']}, Size: {r['size']/1024:.1f} KB, Obfuscated: {r['is_obfuscated']}")
            if r.get('detections'):
                cats = list(r['detections'].keys())
                print(f"   Categories: {', '.join(cats[:5])}")
    
    # Statistics by category
    category_counts = defaultdict(int)
    for r in results:
        for cat in r.get('detections', {}):
            category_counts[cat] += 1
    
    print("\nFingerprinting categories distribution:")
    print("-" * 60)
    for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat}: {count} files")


if __name__ == '__main__':
    # Default directory
    default_dir = 'clearnet_scripts'
    
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = default_dir
    
    if not os.path.exists(directory):
        print(f"Error: Directory '{directory}' not found!")
        sys.exit(1)
    
    output_file = 'fingerprint_analysis.json'
    
    results = analyze_directory(directory, output_file)
    print_summary(results)
    
    print(f"\nDetailed results saved to: {output_file}")
