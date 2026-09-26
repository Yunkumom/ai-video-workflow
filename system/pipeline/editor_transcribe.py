"""Local recognizer entry, executed only with the already installed MLX runtime."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--audio',required=True);parser.add_argument('--model',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not Path(args.model).is_dir(): raise ValueError('本機辨識模型不存在。')
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import mlx_whisper
    result=mlx_whisper.transcribe(args.audio,path_or_hf_repo=args.model,language='zh',word_timestamps=True,verbose=False,
        initial_prompt='臺灣繁體中文逐字稿，保留英文名稱；不要添加未說出的內容。')
    Path(args.output).write_text(json.dumps(result['segments'],ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':main()
