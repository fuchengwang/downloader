import subprocess
import sys
import shutil
import os
import time
import json
import urllib.request
import urllib.parse
import argparse
from pathlib import Path

def get_free_port():
    """获取一个随机空闲端口"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port

def get_rpc_data(method, params=None, port=6800):
    """通过 JSON-RPC 获取 aria2 数据"""
    url = f"http://127.0.0.1:{port}/jsonrpc"
    data = {
        "jsonrpc": "2.0",
        "id": "qwer",
        "method": method,
        "params": params or []
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return None

def hex_to_bitfield(hex_str, num_pieces):
    """将 hex 字符串转换为美观的分片进度条"""
    bar_width = 40
    if not hex_str:
        return "░" * bar_width
    bin_str = bin(int(hex_str, 16))[2:].zfill(len(hex_str) * 4)
    display_bar = ""
    for i in range(bar_width):
        idx = int(i * len(bin_str) / bar_width)
        if idx < len(bin_str) and bin_str[idx] == '1':
            display_bar += "█"
        else:
            display_bar += "░"
    return display_bar

def format_size(size_bytes):
    """格式化字节数为可读单位"""
    size_bytes = float(size_bytes)
    for unit in ['B', 'KiB', 'MiB', 'GiB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TiB"

def get_filename_from_url(url):
    """从 URL 中尝试提取文件名"""
    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    if 'filename' in query_params:
        return urllib.parse.unquote(query_params['filename'][0])
    disposition_keys = ['rscd', 'response-content-disposition', 'content-disposition']
    for key in disposition_keys:
        if key in query_params:
            disposition = urllib.parse.unquote(query_params[key][0])
            if "filename*=" in disposition.lower():
                parts = disposition.lower().split("filename*=")
                val = parts[1].split(";")[0].strip()
                if "utf-8''" in val:
                    return urllib.parse.unquote(val.replace("utf-8''", ""))
            if "filename=" in disposition.lower():
                parts = disposition.lower().split("filename=")
                return parts[1].split(";")[0].strip(' "\'')
    path = parsed_url.path
    filename = os.path.basename(path)
    if not filename:
        return "downloaded_file"
    return urllib.parse.unquote(filename)

def download_file(url, filename=None, extra_headers=None):
    if not shutil.which("aria2c"):
        print("❌ 错误: 未找到 aria2c。请先安装 aria2 (brew install aria2)。")
        return

    if not filename:
        filename = get_filename_from_url(url)

    # 默认下载到 ~/Downloads 文件夹
    downloads_dir = str(Path.home() / "Downloads")
    if not os.path.isabs(filename):
        save_path = os.path.join(downloads_dir, filename)
    else:
        save_path = filename
    
    # 确保目录存在
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # 默认配置
    parsed_url = urllib.parse.urlparse(url)
    domain = parsed_url.netloc
    
    # 基础 Headers
    header_dict = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive"
    }

    # 针对 Quark 网盘的默认 Referer (如果用户没提供)
    if "quark.cn" in domain:
        header_dict["Referer"] = "https://pan.quark.cn/"
    else:
        header_dict["Referer"] = f"{parsed_url.scheme}://{domain}/"

    # !!! 关键修改：移除自动添加的 Sec-Fetch-* Headers !!!
    # 这些 Headers 如果与浏览器实际行为不一致（例如缺少 Sec-Fetch-User），反而会触发 403 风控。
    # 现在的策略是：只发送基础 Header，除非用户显式提供更多。

    # 合并用户传入的 Headers (高优先级，覆盖默认值)
    if extra_headers:
        for h in extra_headers:
            if ":" in h:
                k, v = h.split(":", 1)
                k = k.strip()
                v = v.strip()
                # 针对 Cookie 的特殊处理：防止被错误覆盖或截断
                if k.lower() == "cookie":
                    header_dict["Cookie"] = v
                else:
                    header_dict[k] = v  # 这里的 User-Agent 会覆盖上面的默认值

    rpc_port = get_free_port()
    command = [
        "aria2c",
        "--no-conf",
        url,
        f"--out={os.path.basename(save_path)}",
        f"--dir={os.path.dirname(save_path)}",
        "--check-certificate=false",
        "-x", "16",
        "-s", "64",
        "--min-split-size=1M",
        "--connect-timeout=10",
        "--continue=true",
        "--enable-rpc",
        f"--rpc-listen-port={rpc_port}",
        "--rpc-listen-all=false",
        "--quiet=true"
    ]
    
    # 将字典形式的 headers 加入命令
    for k, v in header_dict.items():
        # 再次确保 quote，防止 shell 解析错误，虽然 subprocess 列表形式相对安全
        command.append(f"--header={k}: {v}")

    print(f"\n🚀 启动引擎 (端口: {rpc_port})...")
    print(f"📂 目标: {save_path}")
    
    # 调试：打印完整的命令行，方便用户复制调试
    debug_cmd = " ".join([f"'{arg}'" if " " in arg or "&" in arg or ";" in arg else arg for arg in command])
    print(f"\n🔍 [调试] 执行命令:\n{debug_cmd}\n")

    process = subprocess.Popen(command, stderr=subprocess.PIPE, text=True)
    
    try:
        connected = False
        for i in range(20):
            if process.poll() is not None:
                stderr_output = process.stderr.read()
                print(f"\n❌ aria2c 启动失败。")
                print(f"--- 错误日志 ---\n{stderr_output}----------------")
                return
            time.sleep(0.5)
            if get_rpc_data("aria2.getVersion", port=rpc_port):
                connected = True
                break
        
        if not connected:
            print(f"\n❌ 无法连接到 aria2 RPC 服务。")
            process.terminate()
            return

        gid = None
        last_status = None
        first_draw = True
        start_time = None
        end_time = None
        downloaded_start_offset = 0
        
        while True:
            active = get_rpc_data("aria2.tellActive", port=rpc_port)
            if active is None or not active.get("result"):
                stopped = get_rpc_data("aria2.tellStopped", [0, 10], port=rpc_port)
                if stopped and stopped.get("result"):
                    target_task = next((s for s in stopped["result"] if s["gid"] == gid), stopped["result"][0]) if gid else stopped["result"][0]
                    last_status = {"result": target_task}
                    if target_task["status"] == "complete":
                        total_len = target_task['totalLength']
                        end_time = time.time()
                        duration = max(0, end_time - (start_time or end_time))
                        status_line = f"[{format_size(total_len)}/{format_size(total_len)} (100.0%) 速度:0.00 B/s 剩余:00:00]"
                        if not first_draw: sys.stdout.write("\033[2A")
                        sys.stdout.write(f"\r\033[K{status_line}\n\r\033[K分片进度: [{'█' * 40}]\n")
                        sys.stdout.flush()
                        print(f"\n✅ 下载成功！")
                        print(f"⏱️  总计耗时: {int(duration // 60):02d}分{int(duration % 60):02d}秒")
                        print(f"📂 保存位置: {save_path}")
                        break
                    elif target_task["status"] == "error":
                        print(f"\n\n❌ 下载失败: {target_task.get('errorMessage', '未知错误')}")
                        break
                    
                if process.poll() is not None: break
                time.sleep(0.5)
                continue

            task = active["result"][0]
            gid = task["gid"]
            last_status = {"result": task}
            total = int(task["totalLength"])
            completed = int(task["completedLength"])
            speed = int(task["downloadSpeed"])
            if start_time is None and speed > 0:
                start_time = time.time(); downloaded_start_offset = completed
            percent = (completed / total * 100) if total > 0 else 0
            
            # 计算预计剩余时间 (ETA)
            eta_str = "未知"
            if speed > 0 and total > 0:
                remaining_bytes = total - completed
                remaining_seconds = remaining_bytes / speed
                if remaining_seconds < 3600:
                    eta_str = f"{int(remaining_seconds // 60):02d}:{int(remaining_seconds % 60):02d}"
                else:
                    eta_str = f"{int(remaining_seconds // 3600):02d}:{int((remaining_seconds % 3600) // 60):02d}:{int(remaining_seconds % 60):02d}"

            status_line = f"[{format_size(completed)}/{format_size(total)} ({percent:.1f}%) 线程:{task.get('connections', '0')} 速度:{format_size(speed)}/s 剩余:{eta_str}]"
            progress_line = f"分片进度: [{hex_to_bitfield(task.get('bitfield', ''), int(task.get('numPieces', 1)))}]"
            if not first_draw: sys.stdout.write("\033[2A")
            sys.stdout.write(f"\r\033[K{status_line}\n\r\033[K{progress_line}\n"); sys.stdout.flush()
            first_draw = False
            if completed >= total and total > 0: 
                time.sleep(0.2); print(f"\n✅ 下载完成！"); break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n🛑 下载已中止。")
    finally:
        process.terminate()
        try: process.wait(timeout=1)
        except: process.kill()

def get_clipboard_content():
    """使用 pbpaste 获取 macOS 剪贴板内容 (不依赖第三方库)"""
    try:
        process = subprocess.Popen(['pbpaste'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        return stdout.strip()
    except Exception:
        return ""

def parse_command_string(cmd_str):
    """
    智能解析剪贴板中的下载命令字符串
    支持格式:
    1. 纯 URL: https://example.com/file.zip
    2. 带引号 URL: "https://example.com/file.zip"
    3. 带参数: "URL" --out "path" --header "Header: Value"
    4. aria2c/python 命令: aria2c "URL" --out ...
    """
    import re
    from argparse import Namespace
    
    cmd_str = cmd_str.strip()
    if not cmd_str: 
        return None

    # 定义需要跳过的命令前缀
    prefixes = ["python", "python3", "aria2c", "curl", "wget"]
    
    # 清除命令前缀
    clean_str = cmd_str
    for pref in prefixes:
        pattern = rf'^{pref}(\d*)\s+'
        clean_str = re.sub(pattern, '', clean_str, flags=re.IGNORECASE)
    # 移除脚本名
    clean_str = re.sub(r'^[\w\-\.]+\.py\s+', '', clean_str, flags=re.IGNORECASE)
    
    print(f"🔍 智能解析输入内容...")
    
    url = None
    out_path = None
    headers = []
    
    # 提取 URL (支持带引号和不带引号)
    # 关键修正：先尝试提取被双引号或单引号包裹的 URL（允许内部有空格）
    # 然后再尝试提取不带引号的 URL
    url = None
    
    # 模式1：双引号包裹的 URL (允许空格)
    url_double_quoted = re.search(r'"(https?://[^"]+)"', clean_str)
    if url_double_quoted:
        url = url_double_quoted.group(1)
    else:
        # 模式2：单引号包裹的 URL (允许空格)
        url_single_quoted = re.search(r"'(https?://[^']+)'", clean_str)
        if url_single_quoted:
            url = url_single_quoted.group(1)
        else:
            # 模式3：不带引号的 URL (不允许空格)
            url_no_quote = re.search(r'(https?://[^\s"\']+)', clean_str)
            if url_no_quote:
                url = url_no_quote.group(1)
    
    # 提取 --out 参数 (支持多种引号格式)
    # 匹配: --out "path" 或 --out 'path' 或 --out path
    out_patterns = [
        r'--out\s+"([^"]+)"',           # --out "path with spaces"
        r"--out\s+'([^']+)'",           # --out 'path with spaces'
        r'--out\s+([^\s"\']+)',         # --out path_no_spaces
    ]
    for pattern in out_patterns:
        out_match = re.search(pattern, clean_str)
        if out_match:
            out_path = out_match.group(1)
            break
    
    # 提取 --header 参数 (改进版：支持单引号和双引号，非贪婪匹配)
    header_patterns = [
        r'--header\s+"([^"]+)"',        # --header "Header: Value"
        r"--header\s+'([^']+)'",        # --header 'Header: Value' - 关键增加
    ]
    for pattern in header_patterns:
        found_headers = re.findall(pattern, clean_str)
        headers.extend(found_headers)
    
    if url and is_valid_url(url):
        print(f"✅ 正则提取成功")
        print(f"   📎 URL: {url[:60]}{'...' if len(url) > 60 else ''}")
        if out_path:
            print(f"   📂 输出: {out_path}")
        if headers:
            print(f"   📋 Headers: {len(headers)} 个")
        return Namespace(
            url=url,
            out=out_path,
            header=headers if headers else None
        )
    
    # ========== 方法3: 最后尝试 - 整个字符串就是 URL ==========
    # 去除首尾引号后检查是否是有效 URL
    stripped = cmd_str.strip().strip("'\"")
    if is_valid_url(stripped):
        print(f"✅ 直接识别为 URL")
        return Namespace(url=stripped, out=None, header=None)

    print(f"❌ 无法从剪贴板内容中提取有效 URL")
    return None

def is_valid_url(url):
    """检查 URL 是否合法"""
    if not url: return False
    # 简单的 http/https 检查
    return url.startswith("http://") or url.startswith("https://")

def download_file_curl(url, filename=None, extra_headers=None):
    """使用 curl 下载文件 (作为 aria2 的备选)"""
    if not shutil.which("curl"):
        print("❌ 错误: 未找到 curl。")
        return

    parsed_url = urllib.parse.urlparse(url)
    domain = parsed_url.netloc
    
    if not filename:
        filename = get_filename_from_url(url)
        
    # 默认下载到 ~/Downloads 文件夹
    downloads_dir = str(Path.home() / "Downloads")
    if not os.path.isabs(filename):
        save_path = os.path.join(downloads_dir, filename)
    else:
        save_path = filename
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    cmd = ["curl", "-L", "-#", "-o", save_path, url] # -L follow redirect, -# progress bar
    
    # 构造 Headers
    # 1. User-Agent
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    cmd.extend(["-A", ua])
    
    # 2. Referer
    referer = f"{parsed_url.scheme}://{domain}/"
    if "quark.cn" in domain:
        referer = "https://pan.quark.cn/"
    cmd.extend(["-e", referer])
    
    # 3. Extra Headers
    if extra_headers:
        for h in extra_headers:
            if ":" in h:
                k, v = h.split(":", 1)
                k = k.strip()
                v = v.strip()
                cmd.extend(["-H", f"{k}: {v}"])

    print(f"\n🚀 启动 curl 引擎...")
    print(f"📂 目标: {save_path}")
    
    # 调试：打印完整的命令行
    debug_cmd = " ".join([f"'{arg}'" if " " in arg or "&" in arg or ";" in arg else arg for arg in cmd])
    print(f"\n🔍 [调试] curl 命令:\n{debug_cmd}\n")
    
    try:
        subprocess.run(cmd, check=True)
        print(f"\n✅ 下载成功！")
        print(f"📂 保存位置: {save_path}")
    except subprocess.CalledProcessError:
        print(f"\n❌ curl 下载失败。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="高级多线程下载脚本")
    parser.add_argument("url", nargs="?", help="下载链接")
    parser.add_argument("--out", "-o", help="指定保存文件名")
    parser.add_argument("--header", action="append", help="自定义 HTTP 请求头")
    parser.add_argument("--curl", action="store_true", help="使用 curl 而不是 aria2 进行下载")
    
    args = parser.parse_args()
    
    # === 统一输入源处理 ===
    raw_input = None
    
    # 1. 优先使用命令行参数 provided via args.url
    if args.url:
        raw_input = args.url
    else:
        # 2. 交互式获取
        try:
            choice = input("请输入下载链接 (或输入 'v' 从剪贴板读取): ").strip()
        except EOFError:
            choice = ""

        if choice.lower() == 'v':
            raw_input = get_clipboard_content()
            if not raw_input:
                print("❌ 剪贴板中没有内容。")
            else:
                print(f"📋 已从剪贴板捕获内容...")
        else:
            raw_input = choice
    
    if not raw_input:
        print("❌ 未提供任何下载链接。")
        sys.exit(0)

    # === 统一解析处理 ===
    # 将所有输入（无论是直接的URL、带参数的命令、还是混合文本）都通过解析器处理
    final_url = None
    final_out = args.out
    final_headers = args.header or []

    parsed = parse_command_string(raw_input)
    
    if parsed and parsed.url:
        final_url = parsed.url
        # 如果解析出了 output 且命令行没有强制指定，则使用解析出的
        if parsed.out and not final_out:
            final_out = parsed.out
        # 合并 headers
        if parsed.header:
            final_headers.extend(parsed.header)
    
    if final_url:
        # 二次清理
        final_url = final_url.replace('&amp;', '&').strip(' "\'')
        
        if not is_valid_url(final_url):
            print(f"\n❌ 错误: 非法的下载链接!")
            print(f"💡 识别到的链接: \"{final_url[:100]}...\"")
            print(f"💡 有效的链接必须以 'http://' 或 'https://' 开头。")
            sys.exit(1)
            
        start_wall_time = time.time()
        
        if args.curl:
             download_file_curl(final_url, filename=final_out, extra_headers=final_headers)
        else:
             download_file(final_url, filename=final_out, extra_headers=final_headers)
        
        # 下载完成后的统计在 download_file 内部处理
    else:
        print("❌ 无法识别有效的下载链接。")
