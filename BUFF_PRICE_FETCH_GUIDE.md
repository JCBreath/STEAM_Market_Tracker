# BUFF价格抓取指南

## 功能说明
`fetch_buff_prices.py` 脚本会：
1. 读取 `steam_market_730_pages_1_3059.json` 中的所有物品
2. 对每个物品调用BUFF API获取价格
3. **每次请求后立即保存**（防止数据丢失）
4. 输出到 `steam_market_with_buff_prices.json`

## 准备工作

### 方法1：浏览器导出Cookie（推荐）

1. **安装Cookie导出插件**
   - Chrome: [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg)
   - Firefox: [Cookie-Editor](https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/)

2. **登录BUFF**
   - 访问: https://buff.163.com/market/csgo
   - 使用网易账号登录

3. **导出Cookies**
   - 点击浏览器插件图标
   - 选择 "Export" → "JSON"
   - 保存为: `~/.buff_cookies.json`
   
   示例路径：
   ```bash
   /home/jim/.buff_cookies.json
   ```

4. **验证Cookie文件**
   ```bash
   cat ~/.buff_cookies.json
   ```
   应该看到类似：
   ```json
   [
     {"name": "session", "value": "xxx..."},
     {"name": "csrf_token", "value": "yyy..."}
   ]
   ```

### 方法2：自动浏览器登录

脚本会自动打开Chrome浏览器，你需要：
1. 在浏览器中手动登录BUFF
2. 登录成功后按回车
3. 脚本会自动保存Cookie

**要求：**
- 已安装Chrome或Chromium浏览器
- 已安装Python依赖：
  ```bash
  conda activate py310
  pip install selenium webdriver-manager
  ```

## 运行脚本

### 首次运行（需要登录）

```bash
cd /home/jim/STEAM_Market_Tracker
conda activate py310
python Python/fetch_buff_prices.py
```

脚本会提示：
```
BUFF LOGIN REQUIRED
Options:
  1. [RECOMMENDED] Export cookies from browser
  2. Open browser automatically
Choose option (1 or 2):
```

选择对应的方法完成登录。

### 后续运行（已有Cookie）

Cookie保存后，直接运行即可：
```bash
python Python/fetch_buff_prices.py
```

脚本会自动加载Cookie并开始抓取。

## 运行特性

### ✅ 自动保存进度
- **每次API请求后立即保存**
- 输出文件：`steam_market_with_buff_prices.json`
- 检查点文件：`steam_market_with_buff_prices.json.checkpoint`

### ✅ 断点续传
如果脚本中断，重新运行会自动从上次停止的位置继续：
```bash
# 脚本会自动检测并显示：
Found checkpoint: resuming from item 1234
```

### ✅ 智能延迟
- 最小延迟：2.0秒
- 实际延迟：2.0-4.0秒随机
- 防止触发BUFF反爬虫限制

### ✅ 匹配策略
对每个Steam物品名称：
1. 在BUFF搜索获取前10个结果
2. 优先精确匹配
3. 其次部分匹配
4. 返回最佳匹配结果

## 输出文件格式

`steam_market_with_buff_prices.json`:
```json
{
  "meta": {
    "source_file": "steam_market_730_pages_1_3059.json",
    "total_items": 2950,
    "processed_items": 1234,
    "last_processed_index": 1233,
    "generated_at_epoch": 1772577898
  },
  "items": [
    {
      // Steam原始字段
      "page": 1,
      "item_name": "AK-47 | Redline (Field-Tested)",
      "quantity": 5432,
      "starting_price": "$12.50",
      "starting_price_usd": 12.50,
      "hash_name": "AK-47 | Redline (Field-Tested)",
      
      // BUFF新增字段
      "buff_sell_price_cny": 85.5,           // BUFF卖价（人民币）
      "buff_sell_num": 234,                   // BUFF在售数量
      "buff_buy_max_price_cny": 82.0,        // BUFF求购最高价
      "buff_buy_num": 45,                     // BUFF求购数量
      "buff_quick_price_cny": 80.0,          // BUFF快速售出价
      "buff_api_status": "success",          // 状态：success/not_found/failed
      "buff_error_msg": null                  // 错误信息（如果有）
    }
  ]
}
```

## 监控进度

### 实时查看最新处理的物品
```bash
tail -f steam_market_with_buff_prices.json
```

### 查看已处理数量
```bash
python3 -c "import json; d=json.load(open('steam_market_with_buff_prices.json')); print(f\"{d['meta']['processed_items']}/{d['meta']['total_items']} items processed\")"
```

### 查看成功率统计
```bash
python3 -c "
import json
d = json.load(open('steam_market_with_buff_prices.json'))
items = d['items']
success = sum(1 for i in items if i['buff_api_status'] == 'success')
not_found = sum(1 for i in items if i['buff_api_status'] == 'not_found')
failed = sum(1 for i in items if i['buff_api_status'] == 'failed')
print(f'Success: {success}, Not Found: {not_found}, Failed: {failed}')
"
```

## 预估时间

- 当前Steam文件有 **2950** 个物品
- 每个请求延迟：**2-4秒**
- 预计总时间：**~2.5-3小时**

可以在后台运行：
```bash
nohup python Python/fetch_buff_prices.py > buff_fetch.log 2>&1 &
echo $!  # 记下进程ID
```

查看日志：
```bash
tail -f buff_fetch.log
```

停止进程：
```bash
kill <进程ID>
# 或
pkill -f "fetch_buff_prices.py"
```

## 常见问题

### Q: Cookie过期怎么办？
A: 重新运行脚本，选择登录选项更新Cookie

### Q: 某些物品在BUFF找不到？
A: 正常现象，会标记为 `buff_api_status: "not_found"`

### Q: 遇到API限流怎么办？
A: 脚本有自动延迟，如果仍然被限流，手动增加延迟：
```python
# 编辑 fetch_buff_prices.py
MIN_DELAY_SECONDS = 3.0  # 改为3秒或更长
```

### Q: 如何重新开始（清除进度）？
```bash
rm steam_market_with_buff_prices.json.checkpoint
```

## 下一步

数据收集完成后，可以：
1. 分析Steam与BUFF价差
2. 找出套利机会
3. 导入到数据库进行深度分析
4. 更新网页查看器显示BUFF价格

---
**注意事项：**
- 遵守BUFF使用条款
- 合理控制请求频率
- 不要分享你的Cookie文件
