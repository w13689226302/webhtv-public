import re
import sys
import time
import urllib.parse
import json
import requests
import urllib3
from pyquery import PyQuery as pq

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    _RE_JUMP = re.compile(r'strU\s*=\s*["\'](.*?)["\']', re.IGNORECASE)
    _RE_VODPLAY = re.compile(r'/vodplay/(\d+)-(\d+)-(\d+)')
    _RE_M3U8_JSON = re.compile(r'player_aaaa\s*=\s*({.*?});', re.DOTALL)
    _RE_M3U8_URL = re.compile(r'https?://[^\s"\'<>]+\.m3u8')
    _RE_M3U8_REL = re.compile(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"')

    _STATIC_CLASSES = [
        {"type_name": "日韩AV", "type_id": "1"}, {"type_name": "国产系列", "type_id": "2"}, 
        {"type_name": "欧美", "type_id": "3"}, {"type_name": "成人动漫", "type_id": "4"},
        {"type_name": "日本有码", "type_id": "7"}, {"type_name": "一本道高清无码", "type_id": "8"},
        {"type_name": "有码中文字幕", "type_id": "9"}, {"type_name": "日本无码", "type_id": "10"},
        {"type_name": "国产视频", "type_id": "15"}, {"type_name": "欧美高清", "type_id": "21"},
        {"type_name": "动漫剧情", "type_id": "22"}
    ]

    def __init__(self):
        self.name = "黄色仓库"
        self.session = requests.Session()
        self.header = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            "pics": "1"
        }
        self.session.headers.update(self.header)
        self.host = self.getDynamicHost()
        self.header['Referer'] = self.host 
        self.session.headers.update({'Referer': self.host})

    def getName(self):
        return self.name

    def getDynamicHost(self):
        fallback, target_url = "http://789067.xyz", "http://hscangku.com"
        temp_header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

        try:
            res = requests.get(target_url, headers=temp_header, verify=False, timeout=8)
            match = self._RE_JUMP.search(res.text)
            
            if match:
                jump_str = match.group(1)
                
                # 合并精简了 URL 拼接逻辑
                if '?u=' in jump_str:
                    origin_enc = urllib.parse.quote(target_url, safe="") if jump_str.endswith('?u=') else ""
                    test_url = f"{jump_str}{origin_enc}&p=/"
                else:
                    test_url = urllib.parse.urljoin(target_url, jump_str)
                
                res_jump = requests.get(test_url, headers=temp_header, verify=False, allow_redirects=True, timeout=10)
                
                # 优先匹配 JS 隐蔽跳转，其次取落地页 URL
                m_js = re.search(r'location\.href\s*=\s*["\'](.*?)["\']', res_jump.text)
                final_url = m_js.group(1) if m_js else res_jump.url
                
                parsed = urllib.parse.urlparse(final_url)
                if parsed.netloc:
                    return f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
        except Exception:
            pass
            
        return fallback

    def init(self, extend):
        pass

    def homeContent(self, filter):
        return {'class': self._STATIC_CLASSES}

    def homeVideoContent(self):
        return self._parse_video_list(f"{self.host}/")

    def categoryContent(self, tid, pg, filter, extend):
        if tid == 'new': return self.homeVideoContent()
            
        data = self._parse_video_list(f"{self.host}/vodtype/{tid}-{pg}.html")
        data.update({'page': int(pg), 'pagecount': 9999, 'limit': 90, 'total': 999999})
        return data

    def searchContent(self, key, quick, page='1'):
        return self._parse_video_list(f"{self.host}/vodsearch/-------------.html?wd={urllib.parse.quote(key)}")

    def _parse_video_list(self, url):
        try:
            root = pq(self.fetch(url).text)
            videos = []
            
            for item in (root('.stui-vodlist li') or root('.ul-img li')).items():
                a_tag = item.find('a')
                vid = a_tag.attr('href')
                
                if not vid or not vid.startswith('/vodplay/'): continue

                title = a_tag.attr('title') or item.find('h4').text()
                if title:
                    img = a_tag.attr('data-original') or item.find('.lazyload').attr('data-original')
                    videos.append({
                        "vod_id": vid,
                        "vod_name": title,
                        "vod_pic": self.getFullUrl(img),
                        "vod_remarks": item.find('.pic-text').text()
                    })
            return {'list': videos}
        except Exception:
            return {'list': []}

    def detailContent(self, array):
        ids = array[0]
        try:
            url = self.getFullUrl(ids)
            root = pq(self.fetch(url).text)
            
            raw_title = root('.stui-pannel__head .title').text() or root('title').text().split(' - ')[0]
            clean_title = raw_title.replace('目录', '').replace('为你推荐', '').strip()
            pic = root('.stui-vodlist__thumb').attr('data-original') or root('img').attr('src')
            play_url = ""
            
            match = self._RE_VODPLAY.search(ids)
            if match:
                vid, sid, nid = match.groups()
                api_url = f"{self.host}/playdata.php?id={vid}&sid={sid}&nid={nid}&_={int(time.time() * 1000)}"
                try:
                    data = self.fetch(api_url).json()
                    if data.get("ok") and data.get("p", {}).get("url"):
                        play_url = f"直链解析${data['p']['url']}"
                except Exception:
                    pass

            if not play_url:
                m3u8_url = self._extract_m3u8(root('script').text())
                if m3u8_url:
                    play_url = f"源码解析${m3u8_url}"
                else:
                    iframe = root('iframe').attr('src')
                    play_url = f"iframe解析${self.getFullUrl(iframe)}" if iframe and 'm3u8' in iframe else f"原页兜底${url}"

            return {"list": [{
                "vod_id": ids,
                "vod_name": clean_title,
                "vod_pic": self.getFullUrl(pic),
                "vod_content": clean_title, 
                "vod_play_from": self.name,
                "vod_play_url": play_url
            }]}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "playUrl": "", "url": id, "header": self.header}

    def _extract_m3u8(self, text):
        match = self._RE_M3U8_JSON.search(text)
        if match:
            try:
                url = json.loads(match.group(1).replace('\\/', '/')).get('url')
                if url and '.m3u8' in url: return self.getFullUrl(url)
            except Exception: pass
            
        urls = self._RE_M3U8_URL.findall(text)
        if urls: return urls[0]
        
        rel_urls = self._RE_M3U8_REL.findall(text)
        if rel_urls: return self.getFullUrl(rel_urls[0])
            
        return None

    def getFullUrl(self, url):
        return urllib.parse.urljoin(self.host + "/", url) if url else ""

    def fetch(self, url):
        return self.session.get(url, verify=False, timeout=10)

    def localProxy(self, param):
        return {}
