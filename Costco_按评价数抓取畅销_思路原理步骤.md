# Costco 按评价数抓取畅销：思路、原理、步骤

## 1. 目标
- 目标：在 Costco 分类页中，按 `review_count`（评价数）倒序，得到畅销 Top N。
- 本次结果：已生成 Top50 文件。

结果文件：
- `download/costco_top50_by_reviews.csv`

## 2. 抓取思路
- 不依赖站内 `sort by review count`（因为前台没有这个排序项）。
- 先进入目标分类页（如 Snacks）。
- 在页面已渲染的商品卡片中提取：
  - 商品名称
  - 商品链接
  - 评价数（review_count）
- 本地排序：按评价数降序。
- 输出 CSV：保留 `rank, name, review_count, url`。

## 3. 原理说明

### 3.1 为什么不用 `requests` 直连
- Costco 存在风控（Akamai），同一机器下 `requests` 可能直接返回 `Access Denied`。
- 因此采用浏览器自动化上下文（MCP Playwright 浏览器），让页面按真实前端流程加载。

### 3.2 评价数提取原理
- 优先从评分相关元素的 `aria-label` 提取，例如：
  - `Based on 2,844 reviews`
- 回退方案：从卡片文本中匹配括号数字，如 `(2,844)`。
- 提取后做数字清洗：去逗号并转整数。

### 3.3 排序与去重原理
- 以 `url` 作为商品主键去重。
- 同一商品出现多次时，保留更大的评价数。
- 最终按 `review_count` 倒序，截取前 50。

## 4. 执行步骤（本次实际执行）
1. 打开 Costco 目标页（Snacks，Most Viewed）。
2. 通过页面快照确认商品区已渲染。
3. 在页面执行 JS，批量抽取商品 `name/url/reviewCount`。
4. 将抽取结果写入本地数据处理流程（去重 + 排序 + Top50）。
5. 导出 CSV 到 `download/costco_top50_by_reviews.csv`。

## 5. 字段定义
- `rank`：排序名次（1 开始）
- `name`：商品名
- `review_count`：评价数（整数）
- `url`：商品详情页链接

## 6. 局限与注意事项
- 评价数是“历史评价热度”的代理指标，不等同于真实销量。
- 页面实验/结构变化会影响选择器，需要按实际 DOM 微调。
- 地区、仓库、配送设置会影响可见商品集合。

## 7. 复用建议
- 如果要 Top100/Top200：只改截取数量即可。
- 如果要提高稳定性：增加多页抓取并合并去重后再排序。
- 如果再次出现风控页：优先使用浏览器上下文，不走 `requests`。
