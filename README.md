# STEAM Market Tracker

一个简单的 CS:GO 市场追踪工具，支持同时抓取：

- Steam Community Market
- 网易 BUFF

## 快速开始

```bash
python3 Python/csgo_market_tracker.py "bloodsport"
```

## 导出 CSV / JSON

```bash
python3 Python/csgo_market_tracker.py "ak-47" --csv output.csv --json output.json
```

## 输出字段

- `name`: 物品名
- `steam_sell_price_text`: Steam 展示价格
- `steam_sell_price_usd`: Steam 价格（USD 浮点）
- `steam_sell_listings`: Steam 在售数量
- `buff_sell_price_cny`: BUFF 最低在售价（CNY）
- `buff_sell_num`: BUFF 在售数量
- `buff_buy_price_cny`: BUFF 最高求购价（CNY）
- `buff_buy_num`: BUFF 求购数量

## 依赖

- Python 3.9+
- 标准库（无需额外三方包）

## 说明

- BUFF 接口可能受到地区、风控、频率限制影响。
- Steam 接口也有请求频率限制，失败时可稍后重试。

## 代理拦截排障

如果你在公司/云环境遇到 `Tunnel connection failed: 403 Forbidden`：

```bash
# 1) 忽略环境代理，直连
python3 Python/csgo_market_tracker.py "AK-47 | Bloodsport (Field-Tested)" --no-proxy

# 2) 手动指定可用代理
python3 Python/csgo_market_tracker.py "AK-47 | Bloodsport (Field-Tested)" --proxy http://127.0.0.1:7890
```

脚本默认行为：若检测到代理隧道失败，会自动再尝试一次直连。

