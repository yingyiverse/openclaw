#!/usr/bin/env python3
"""
火山引擎播客TTS API客户端
使用WebSocket流式生成双人播客音频

需要: Python 3.9+, websocket-client
运行: pip install websocket-client
"""

import asyncio
import json
import uuid
import os
import struct
import websocket
import argparse
import base64
import hmac
import hashlib
import time
from typing import List, Dict, Optional


class PodcastTTSClient:
    """火山引擎播客TTS客户端"""
    
    def __init__(self, app_id: str, access_key: str, secret_key: str):
        self.app_id = app_id
        self.access_key = access_key
        self.secret_key = secret_key
        self.ws = None
        self.audio_chunks: List[bytes] = []
        self.round_texts: List[Dict] = []
        
    def _generate_auth(self) -> tuple:
        """生成认证信息"""
        timestamp = str(int(time.time()))
        message = f"WSS\n{self.app_id}\n{timestamp}\n"
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode(), 
                message.encode(), 
                hashlib.sha256
            ).digest()
        ).decode()
        return timestamp, signature
    
    def _create_frame(self, event_type: int, payload: dict, session_id: str = None) -> bytes:
        """创建WebSocket二进制帧"""
        if session_id is None:
            session_id = str(uuid.uuid4())
            
        payload_bytes = json.dumps(payload).encode('utf-8')
        payload_len = len(payload_bytes)
        
        # 构建帧头
        # Byte 0: version(4bit) | header_size(4bit) = 0x11
        # Byte 1: message_type(4bit) | flags(4bit) = 0x20
        # Byte 2: serialization(4bit) | compression(4bit) = 0x10
        # Byte 3: reserved = 0x00
        
        frame = bytearray()
        frame.append(0x11)  # version=1, header=4
        frame.append(0x20)  # type=2(request)
        frame.append(0x10)  # JSON, no compression
        frame.append(0x00)  # reserved
        
        # Event type (4 bytes)
        frame.extend(struct.pack('>I', event_type))
        
        # Session ID
        session_id_bytes = session_id.encode('utf-8')
        frame.extend(struct.pack('>I', len(session_id_bytes)))
        frame.extend(session_id_bytes)
        
        # Payload
        frame.extend(struct.pack('>I', payload_len))
        frame.extend(payload_bytes)
        
        return bytes(frame), session_id
    
    def _parse_response(self, data: bytes) -> dict:
        """解析响应帧"""
        if len(data) < 8:
            return None
            
        # 解析header
        msg_type = data[1]
        event_type = struct.unpack('>I', data[4:8])[0]
        
        # 获取session_id
        session_len = struct.unpack('>I', data[8:12])[0]
        session_id = data[12:12+session_len].decode('utf-8')
        
        # 获取payload
        payload_start = 12 + session_len
        payload_len = struct.unpack('>I', data[payload_start:payload_start+4])[0]
        
        payload = None
        audio_data = None
        
        if payload_len > 0 and len(data) >= payload_start + 4 + payload_len:
            payload_data = data[payload_start+4:payload_start+4+payload_len]
            try:
                payload = json.loads(payload_data.decode('utf-8'))
            except:
                pass
            
            # 检查是否有音频数据
            audio_start = payload_start + 4 + payload_len
            if len(data) > audio_start:
                audio_data = data[audio_start:]
        
        return {
            'event': event_type,
            'session': session_id,
            'payload': payload,
            'audio': audio_data
        }
    
    async def generate(
        self, 
        nlp_texts: list, 
        output_file: str = None,
        format: str = 'mp3',
        sample_rate: int = 24000
    ) -> List[Dict]:
        """生成播客音频"""
        
        # 认证
        timestamp, signature = self._generate_auth()
        
        # WebSocket URL
        url = "wss://openspeech.bytedance.com/api/v3/sami/podcasttts"
        headers = {
            "X-Api-App-Id": self.app_id,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": "volc.service_type.10050",
            "X-Api-App-Key": "aGjiRDfUWi",
            "Authorization": f"HMAC256 {self.access_key}:{signature}",
            "X-Api-Request-Id": str(uuid.uuid4())
        }
        
        print(f"Connecting to {url}...")
        self.ws = websocket.create_connection(url, header=headers, timeout=30)
        print("Connected!")
        
        # 构建请求
        payload = {
            "input_id": str(uuid.uuid4()),
            "action": 3,  # 对话文本模式
            "use_head_music": False,
            "audio_config": {
                "format": format,
                "sample_rate": sample_rate,
                "speech_rate": 0
            },
            "nlp_texts": nlp_texts,
            "speaker_info": {
                "random_order": False,
                "speakers": [
                    "zh_male_dayixiansheng_v2_saturn_bigtts",
                    "zh_female_mizaitongxue_v2_saturn_bigtts"
                ]
            },
            "aigc_watermark": False
        }
        
        # 发送StartSession
        request_frame, session_id = self._create_frame(150, payload)
        self.ws.send(request_frame, opcode=websocket.ABNF.OPCODE_BINARY)
        print(f"Session started: {session_id}")
        
        # 接收响应
        while True:
            try:
                response = self.ws.recv()
                if not response:
                    break
                    
                parsed = self._parse_response(response)
                if not parsed:
                    continue
                
                event = parsed['event']
                
                if event == 360:  # RoundStart
                    if parsed['payload']:
                        text = parsed['payload'].get('text', '')
                        speaker = parsed['payload'].get('speaker', '')
                        print(f"[{speaker}]: {text[:30]}...")
                        self.round_texts.append({'speaker': speaker, 'text': text})
                        
                elif event == 361:  # Audio
                    if parsed['audio']:
                        self.audio_chunks.append(parsed['audio'])
                        
                elif event == 362:  # RoundEnd
                    print("[Round End]")
                    
                elif event == 363:  # End
                    if parsed['payload'] and 'meta_info' in parsed['payload']:
                        audio_url = parsed['payload']['meta_info'].get('audio_url', '')
                        print(f"[Audio URL]: {audio_url}")
                    print("[Podcast End]")
                    break
                    
                elif event == 152:  # SessionFinished
                    break
                    
            except Exception as e:
                print(f"Error: {e}")
                break
        
        # 关闭连接
        try:
            self.ws.close()
        except:
            pass
        
        # 保存音频
        if output_file and self.audio_chunks:
            audio_data = b''.join(self.audio_chunks)
            with open(output_file, 'wb') as f:
                f.write(audio_data)
            print(f"Saved: {output_file} ({len(audio_data)} bytes)")
        
        return self.round_texts


async def main():
    parser = argparse.ArgumentParser(description='火山引擎播客TTS')
    parser.add_argument('--input', '-i', required=True, help='输入JSON文件')
    parser.add_argument('--output', '-o', default='podcast.mp3', help='输出音频文件')
    parser.add_argument('--format', default='mp3', help='音频格式')
    parser.add_argument('--sample-rate', type=int, default=24000, help='采样率')
    args = parser.parse_args()
    
    # 读取输入
    with open(args.input, 'r', encoding='utf-8') as f:
        nlp_texts = json.load(f)
    
    # 获取凭证
    app_id = os.environ.get('VOLCENGINE_APP_ID')
    access_key = os.environ.get('VOLCENGINE_ACCESS_KEY')
    secret_key = os.environ.get('VOLCENGINE_SECRET_KEY')
    
    if not all([app_id, access_key, secret_key]):
        print("错误: 请设置环境变量 VOLCENGINE_APP_ID, VOLCENGINE_ACCESS_KEY, VOLCENGINE_SECRET_KEY")
        return
    
    # 生成
    client = PodcastTTSClient(app_id, access_key, secret_key)
    await client.generate(nlp_texts, args.output, args.format, args.sample_rate)


if __name__ == '__main__':
    import sys
    if sys.version_info >= (3, 9):
        asyncio.run(main())
    else:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
