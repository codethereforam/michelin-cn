# 米其林中国餐厅抓取：思路与原理

## 1. 任务目标
- 从米其林指南站点获取中国大陆餐厅数据。
- 按城市拆分为独立 JSON 文件。
- 输出一个城市索引文件，汇总每个城市的数量与文件名。

## 2. 总体策略
本任务没有采用“爬 HTML 页面 + 解析 DOM”的方式，而是采用“定位网页背后的数据接口，直接请求结构化 JSON”。

原因：
- 页面是前端渲染，HTML 里通常没有完整数据。
- 接口返回结构化字段，稳定、可分页、易验证。
- 相比浏览器自动化（如 Playwright）更快、更少误差、维护成本更低。

## 3. 如何做网络探测（找到真实数据源）
标准流程：
1. 打开目标页面（例如南京餐厅列表页）。
2. 打开浏览器开发者工具（F12）并进入 Network。
3. 刷新页面，过滤 Fetch/XHR 请求。
4. 定位“返回餐厅列表 JSON”的请求。
5. 记录以下信息：
   - Request URL
   - Request Method
   - Request Headers
   - Request Payload
   - Response JSON 结构

本任务定位到的核心接口是 Algolia 多查询端点：
- `POST https://8nvhrd7onv-dsn.algolia.net/1/indexes/*/queries`

## 4. 接口调用原理
米其林前端将餐厅内容存储在 Algolia 索引中。页面加载时，前端会向 Algolia 发起查询并返回 hits（餐厅记录）。

### 4.1 关键请求头
- `x-algolia-application-id`
- `x-algolia-api-key`
- `x-algolia-agent`

这些值可以从网页实际请求中获取，用于复现前端同源查询。

### 4.2 关键请求体字段
- `indexName`: 目标索引（示例：`prod-restaurants-zh_CN_sort_geo` 或同类中文索引）。
- `attributesToRetrieve`: 指定要返回的字段列表。
- `facets`: 声明可聚合字段。
- `filters`: 强过滤条件。
- `optionalFilters`: 弱过滤条件（排序和相关性层面的附加约束）。
- `hitsPerPage`: 每页条数。
- `page`: 当前页（从 0 开始）。

## 5. 为什么知道可以取 `main_desc`
不是猜测，而是“可见字段 + 实测验证”：
1. 在请求结构中观察到 `attributesToRetrieve` 是可配置返回字段。
2. 将 `main_desc` 加入或保留在该列表。
3. 检查响应 `hits`，确认字段存在且有值。

结论：字段是否可用，以响应结果为准。

## 6. 为什么知道可用 `country.slug:cn`
依据是“facets 暴露 + 过滤实测”：
1. 请求里 `facets` 包含 `country.slug`，说明这是可过滤维度。
2. 在 `filters` 中加入 `country.slug:cn`。
3. 查看响应是否只剩中国大陆数据（城市与数量符合预期）。

常用过滤示例：
- `status:Published AND country.slug:cn`

## 7. 全量抓取与分页机制
Algolia 单次返回有限（如 48 或 100 条），必须分页：
1. 从 `page=0` 开始请求。
2. 读取返回中的 `nbPages`（总页数）或依据 hits 为空结束。
3. 循环请求 `page=1,2,3...` 直到结束。
4. 合并所有页 hits 为全量列表。

这样可以稳定拿到中国大陆全量餐厅，而不是只拿首屏数据。

## 8. 按城市拆分输出
处理步骤：
1. 从每条 hit 中读取城市字段（通常为 `city.name` 与 `city.slug`）。
2. 按城市分组。
3. 逐城市写文件：
   - `download/michelin_china_<city_slug>_restaurants.json`
4. 生成索引文件：
   - `download/michelin_china_city_index.json`
   - 内容包含总数、城市数、每城文件名和数量。

## 9. 餐厅详情是如何获取的
餐厅详情不是通过“点开每家餐厅页再抓”，而是直接来自列表接口返回的记录字段。常见字段包括：
- `name`
- `city`
- `cuisines`
- `price_category`
- `michelin_award`
- `url`
- `main_desc`
- `phone`
- 以及地理与图片相关字段（视索引而定）

若某字段缺失，优先检查：
- 是否包含在 `attributesToRetrieve`
- 索引中该字段是否真实存在

## 10. 为什么有时会用 Playwright
Playwright 并不是“错误方案”，而是另一种策略。

更适合 Playwright 的情况：
- 接口被强混淆或签名复杂，短期难以复现。
- 必须模拟登录、点击、滚动、验证码流程。
- 目标数据只在前端交互后动态产生。

更适合直接接口的情况：
- 已定位到稳定 JSON 数据端点。
- 参数和分页规则清晰。
- 目标是高效全量拉取。

本次属于后者，所以最终选了 API 方案。

## 11. 稳定性与质量控制
建议做以下校验：
- 总条数校验：分页合并后的条数是否稳定。
- 去重校验：用 `identifier/objectID + url` 去重。
- 城市分组校验：每城文件条数与索引一致。
- 样本抽检：随机抽取若干餐厅核对官网页面。
- 重跑一致性：同日多次抓取总量变化应可解释（如榜单更新）。

## 12. 风险与注意事项
- 网站索引名、字段名、密钥可能变更，脚本需可配置。
- 部分字段可能为空，落盘时要容错。
- 需遵守目标站点服务条款与合理请求频率，避免高并发冲击。

## 13. 可复用 SOP（给后续类似任务）
1. 先抓包定位真实 JSON 源。
2. 记录最小可复现请求（URL、Headers、Payload）。
3. 小样本验证字段与过滤条件。
4. 加分页拿全量。
5. 结构化落盘（分组文件 + 总索引）。
6. 做完整性和一致性校验。

---
这份文档描述的是“方法论 + 工程实现原则”。即使目标站点变了，也可以按同样流程快速迁移。