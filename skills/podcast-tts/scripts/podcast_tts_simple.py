#!/usr/bin/env python3
"""
火山引擎播客TTS客户端 - 简化版
Python 3.9+ required
"""

import websocket
import json
import uuid
import struct
import base64
import hmac
import hashlib
import time
import requests


def create_frame(action, payload, session_id=None):
    """创建WebSocket二进制帧"""
    if session_id is None:
        session_id = str(uuid.uuid4())
    
    payload_bytes = json.dumps(payload).encode('utf-8')
    
    # 按文档构建帧
    # Byte 0: version(4bit) + header_size(4bit) = 0x11
    # Byte 1: message_type(4bit) + flags(4bit) = 0x10 (type=1, flags=0)
    # Byte 2: serialization(4bit) + compression(4bit) = 0x10 (JSON, no compression)
    # Byte 3: reserved = 0x00
    
    frame = bytearray()
    frame.append(0x11)
    frame.append(0x10)
    frame.append(0x10)
    frame.append(0x00)
    
    # 添加payload长度和内容
    frame.extend(struct.pack('>I', len(payload_bytes)))
    frame.extend(payload_bytes)
    
    return bytes(frame), session_id


def generate_podcast(nlp_texts, app_id, access_key, secret_key, 
                   speakers=None, output_file='podcast.mp3'):
    """生成播客音频"""
    
    # 生成签名
    timestamp = str(int(time.time()))
    message = f'WSS\n{app_id}\n{timestamp}\n'
    signature = base64.b64encode(
        hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
    ).decode()
    
    # WebSocket连接
    url = 'wss://openspeech.bytedance.com/api/v3/sami/podcasttts'
    headers = {
        'X-Api-App-Id': app_id,
        'X-Api-Access-Key': access_key,
        'X-Api-Resource-Id': 'volc.service_type.10050',
        'X-Api-App-Key': 'aGjiRDfUWi',
        'Authorization': f'HMAC256 {access_key}:{signature}',
        'X-Api-Request-Id': str(uuid.uuid4())
    }
    
    if speakers is None:
        speakers = ['zh_male_xiaolei_v2_saturn_bigtts', 
                   'zh_male_liufei_v2_saturn_bigtts']
    
    # 构建payload
    payload = {
        'input_id': str(uuid.uuid4()),
        'action': 3,
        'use_head_music': False,
        'audio_config': {'format': 'mp3', 'sample_rate': 24000, 'speech_rate': 0},
        'nlp_texts': nlp_texts,
        'speaker_info': {'random_order': False, 'speakers': speakers},
        'aigc_watermark': False,
        'input_info': {'return_audio_url': True}
    }
    
    # 创建连接
    ws = websocket.create_connection(url, header=headers, timeout=30)
    
    # 发送请求
    frame, session_id = create_frame(3, payload)
    ws.send(frame, opcode=websocket.ABNF.OPCODE_BINARY)
    
    # 接收响应
    audio_chunks = []
    audio_url = None
    
    while True:
        data = ws.recv()
        if not data:
            break
            
        if len(data) >= 8:
            event = struct.unpack('>I', data[4:8])[0]
            
            if event == 360:  # PodcastRoundStart
                print(f"Processing round...")
            elif event == 361:  # Audio
                if len(data) > 12:
                    audio_chunks.append(data[12:])
            elif event == 363:  # End
                break
    
    ws.close()
    
    # 保存或下载音频
    if audio_chunks:
        with open(output_file, 'wb') as f:
            for chunk in audio_chunks:
                f.write(chunk)
        print(f"Saved: {output_file}")
        return output_file
    
    return None


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', default='podcast.mp3')
    args = parser.parse_args()
    
    # 读取脚本
    with open(args.input) as f:
        nlp_texts = json.load(f)
    
    # 环境变量
    import os
    app_id = os.environ.get('VOLCENGINE_APP_ID')
    access_key = os.environ.get('VOLCENGINE_ACCESS_KEY')
    secret_key = os.environ.get('VOLCENGINE_SECRET_KEY')
    
    if not all([app_id, access_key, secret_key]):
        print("Please set VOLCENGINE_APP_ID, VOLCENGINE_ACCESS_KEY, VOLCENGINE_SECRET_KEY")
        exit(1)
    
    generate_podcast(nlp_texts, app_id, access_key, secret_key, output_file=args.output)
