import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
import json
import asyncio
from datetime import datetime
import random
import socket
import aiohttp
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import time
import os
import threading

# --- NHẬP TOKEN TRỰC TIẾP VÀO ĐÂY ---
TOKEN = "MTQyNDAyMzI3MDI4OTU3NjA2Nw.GkRe8N.rlyEvbQ__lcjpO1CcoTi8W2YZ6WOQaGQDL8AgY"

PREFIX = '!'

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Cache proxy
proxy_cache = {
    'all': [],
    'alive': [],
    'last_update': None,
    'last_scan': None,
    'is_scanning': False
}

SCAN_CONFIG = {
    'timeout': 3,
    'max_workers': 20,
    'max_proxy_to_scan': 300
}

# --- CÁC HÀM LẤY PROXY ---

def fetch_proxy_from_free_proxy_list():
    proxies = []
    try:
        url = "https://free-proxy-list.net/"
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'id': 'proxylisttable'})
        if table:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 8:
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    proxies.append(f"{ip}:{port}")
    except Exception as e:
        print(f"Error free-proxy-list: {e}")
    return proxies

def fetch_proxy_from_github():
    proxies = []
    try:
        urls = [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"
        ]
        for url in urls:
            try:
                response = requests.get(url, timeout=10)
                lines = response.text.strip().split('\n')
                for line in lines:
                    if ':' in line:
                        proxies.append(line.strip())
            except:
                continue
    except Exception as e:
        print(f"Error github: {e}")
    return proxies

def fetch_proxy_from_geonode():
    proxies = []
    try:
        for page in range(1, 2):
            url = f"https://proxylist.geonode.com/api/proxy-list?limit=500&page={page}"
            response = requests.get(url, timeout=10)
            data = response.json()
            if 'data' in data:
                for item in data['data']:
                    ip = item.get('ip')
                    port = item.get('port')
                    if ip and port:
                        proxies.append(f"{ip}:{port}")
    except Exception as e:
        print(f"Error geonode: {e}")
    return proxies

# --- KIỂM TRA PROXY SỐNG ---

def check_proxy_socket_sync(proxy_str, timeout=3):
    try:
        ip, port = proxy_str.split(':')
        port = int(port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except:
        return False

def scan_proxies_sync(proxy_list):
    alive = []
    total = len(proxy_list)
    
    if total == 0:
        return []
    
    if total > SCAN_CONFIG['max_proxy_to_scan']:
        proxy_list = random.sample(proxy_list, SCAN_CONFIG['max_proxy_to_scan'])
    
    print(f"🔍 Đang quét {len(proxy_list)} proxy...")
    
    with ThreadPoolExecutor(max_workers=SCAN_CONFIG['max_workers']) as executor:
        futures = {executor.submit(check_proxy_socket_sync, p): p for p in proxy_list}
        
        for i, future in enumerate(futures):
            try:
                if future.result(timeout=SCAN_CONFIG['timeout'] + 1):
                    alive.append(futures[future])
            except:
                pass
            
            if (i + 1) % 50 == 0:
                print(f"📊 Đã quét: {i+1}/{total} | Sống: {len(alive)}")
    
    print(f"✅ Tìm thấy {len(alive)} proxy sống")
    return alive

# --- TỔNG HỢP PROXY ---

def collect_and_scan_sync():
    all_proxies = []
    
    sources = [
        ('free-proxy-list', fetch_proxy_from_free_proxy_list),
        ('github', fetch_proxy_from_github),
        ('geonode', fetch_proxy_from_geonode),
    ]
    
    for name, func in sources:
        try:
            proxies = func()
            print(f"✅ {name}: {len(proxies)} proxy")
            all_proxies.extend(proxies)
        except Exception as e:
            print(f"❌ {name}: Lỗi - {e}")
    
    unique_proxies = list(set(all_proxies))
    print(f"📊 Tổng proxy độc nhất: {len(unique_proxies)}")
    
    alive_proxies = scan_proxies_sync(unique_proxies)
    
    proxy_cache['all'] = unique_proxies
    proxy_cache['alive'] = alive_proxies
    proxy_cache['last_scan'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proxy_cache['is_scanning'] = False
    
    return alive_proxies

# --- HÀM BẮT ĐẦU QUÉT ---

async def start_scan():
    if proxy_cache['is_scanning']:
        return None
    
    proxy_cache['is_scanning'] = True
    
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, collect_and_scan_sync)
    
    return result

# --- LỆNH DISCORD ---

@bot.command(name='scan')
async def scan_proxy_cmd(ctx):
    if proxy_cache['is_scanning']:
        await ctx.send("⏳ Đang quét proxy, vui lòng đợi...")
        return
    
    status_msg = await ctx.send("🔄 Đang thu thập và quét proxy... Vui lòng đợi (1-2 phút)")
    
    try:
        alive = await start_scan()
        
        if alive is None:
            await status_msg.edit(content="❌ Quét bị lỗi hoặc đã có quá trình khác đang chạy!")
            return
        
        if not alive:
            await status_msg.edit(content="❌ Không tìm thấy proxy sống nào!")
            return
        
        filename = f"proxy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        content = f"# Proxy List - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        content += f"# Total: {len(alive)}\n\n"
        content += "\n".join(alive)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        
        embed = discord.Embed(
            title="✅ Quét proxy thành công!",
            description=f"Tìm thấy **{len(alive)}** proxy sống",
            color=discord.Color.green()
        )
        embed.add_field(name="Tổng thu thập", value=str(len(proxy_cache['all'])), inline=True)
        embed.add_field(name="Proxy sống", value=str(len(alive)), inline=True)
        embed.add_field(name="Tỷ lệ sống", value=f"{round(len(alive)/len(proxy_cache['all'])*100, 2)}%", inline=True)
        embed.set_footer(text=f"Quét lúc: {proxy_cache['last_scan']}")
        
        await status_msg.delete()
        await ctx.send(embed=embed, file=discord.File(filename))
        
        os.remove(filename)
        
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(alive)} proxy sống | {PREFIX}scan"
        ))
        
    except Exception as e:
        proxy_cache['is_scanning'] = False
        await status_msg.edit(content=f"❌ Lỗi: {str(e)}")

@bot.command(name='proxy')
async def get_proxy(ctx, count: int = 20):
    if count > 50:
        count = 50
    
    if not proxy_cache['alive']:
        await ctx.send("🔄 Chưa có proxy sống! Dùng `!scan` để quét.")
        return
    
    proxies = proxy_cache['alive'][:count]
    
    embed = discord.Embed(
        title=f"📋 Proxy sống ({len(proxies)}/{len(proxy_cache['alive'])})",
        color=discord.Color.blue()
    )
    
    text = "\n".join([f"`{p}`" for p in proxies])
    if len(text) > 1000:
        text = text[:1000] + "\n...(còn tiếp)"
    
    embed.add_field(name="Danh sách", value=text, inline=False)
    embed.set_footer(text=f"Cập nhật: {proxy_cache['last_scan'] or 'Chưa quét'}")
    
    await ctx.send(embed=embed)

@bot.command(name='proxy_stats')
async def proxy_stats(ctx):
    total = len(proxy_cache['all'])
    alive = len(proxy_cache['alive'])
    rate = round(alive/total*100, 2) if total > 0 else 0
    
    embed = discord.Embed(
        title="📊 Thống kê Proxy",
        color=discord.Color.blue()
    )
    embed.add_field(name="Tổng thu thập", value=str(total), inline=True)
    embed.add_field(name="Proxy sống", value=str(alive), inline=True)
    embed.add_field(name="Tỷ lệ sống", value=f"{rate}%", inline=True)
    embed.add_field(name="Trạng thái", value="Đang quét" if proxy_cache['is_scanning'] else "Sẵn sàng", inline=True)
    embed.add_field(name="Lần quét cuối", value=proxy_cache['last_scan'] or "Chưa quét", inline=False)
    
    await ctx.send(embed=embed)

# --- TASK TỰ ĐỘNG SCAN MỖI GIỜ ---

@tasks.loop(hours=1)
async def auto_scan():
    print("🔄 Tự động quét proxy...")
    try:
        alive = await start_scan()
        print(f"✅ Đã quét xong! Proxy sống: {len(alive) if alive else 0}")
    except Exception as e:
        print(f"❌ Lỗi tự động quét: {e}")

# --- SỰ KIỆN ON_READY ---

@bot.event
async def on_ready():
    print(f'✅ Bot đã sẵn sàng!')
    print(f'📊 Tên bot: {bot.user.name}')
    print(f'🆔 ID: {bot.user.id}')
    
    # Quét proxy lần đầu
    print("🔄 Bắt đầu quét proxy lần đầu...")
    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            alive = await loop.run_in_executor(pool, collect_and_scan_sync)
        print(f"✅ Đã quét xong! Proxy sống: {len(alive)}")
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(alive)} proxy sống | {PREFIX}scan"
        ))
    except Exception as e:
        print(f"❌ Lỗi quét lần đầu: {e}")
    
    # Bắt đầu auto scan
    auto_scan.start()

# --- CHẠY BOT ---
if __name__ == "__main__":
    bot.run(TOKEN)
