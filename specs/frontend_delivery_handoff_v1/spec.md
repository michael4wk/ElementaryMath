# 小学数学结构化知识库前端独立交付补齐规范（Spec v1.1）

## 1. 背景与重审结论

基于最新目录重组结果，当前仓库已形成 `docs/` 与 `specs/` 分层，且已有前端交付就绪说明文档。项目当前事实状态如下：

- 已具备结构化数据底座、质量门禁、核心查询接口与运行说明
- 已产出前端可对接说明（`docs/delivery/FRONTEND_DELIVERY_READINESS.md`）
- 尚未形成机器可读 API 契约文件（OpenAPI）
- 接口浏览器跨域访问策略尚未标准化（CORS/OPTIONS）
- 联调资产分散，尚未形成“可直接移交前端团队”的统一交付包

本规范目标是在不打断并行优化主线的前提下，补齐前后端嫁接层资产，形成可审计、可复用、可独立联调的交付标准。

## 2. 范围

## 2.1 In Scope（本次纳入）

- 基于现有实现建立并发布 v1 机器可读 API 契约（OpenAPI 3.x）
- 固化前端最小可用接口集与参数语义
- 建立浏览器访问所需 CORS 与 `OPTIONS` 预检规范
- 产出统一前端移交文档包（接入手册、环境矩阵、示例集、变更记录）
- 建立契约变更治理与兼容性校验流程

## 2.2 Out of Scope（本次不纳入）

- 重构结构化流水线核心算法与质量策略实现
- 大规模重命名既有业务对象与存量路径
- 推翻既有 API Key 鉴权体系

## 3. 当前基线

## 3.1 文档与目录基线

- 项目导航：`README.md`
- 实施与接口说明：`README_IMPLEMENTATION.md`
- 前端交付现状：`docs/delivery/FRONTEND_DELIVERY_READINESS.md`
- Spec 套件目录：`specs/README.md`

## 3.2 接口与质量基线

- 当前接口已覆盖目录、主题、题目、检索、图谱、质量与鉴权域
- 当前质量指标达到“可对接”水平（以 `artifacts/acceptance/report.md` 为准）
- 当前门禁可放行，阻断项为 0

## 4. 目标

## 4.1 业务目标

- 前端开发者拿到交付包后，可在不了解底层流水线细节情况下独立开发页面与联调
- 后端在持续优化底座时不阻塞前端迭代，双方通过契约协同

## 4.2 量化目标

- OpenAPI 覆盖率：前端最小接口集 100% 纳入契约
- 契约一致性：OpenAPI 与接口实测一致率 100%
- 跨域可用性：浏览器预检与正式请求通过率 100%
- 文档完备性：前端移交文档包 100% 落位到约定目录
- 联调可用性：前端开发者仅凭文档可独立跑通核心场景

## 5. 设计原则

- 契约先行：先固化接口契约，再做实现增强
- 兼容优先：新增优先、弃用声明、破坏性变更延后
- 双轨并行：低冲突文档交付先行，高冲突改造后置
- 目录对齐：遵循 `docs/` 与 `specs/` 分层，不新增根目录散落文档
- 可审计：变更、验证、发布均留痕可追溯

## 6. 交付架构

## 6.1 交付包组成与落位路径

- API 契约：`docs/delivery/api/openapi.yaml`
- 接入手册：`docs/delivery/api/frontend-integration-guide.md`
- 环境矩阵：`docs/delivery/api/environment-matrix.md`
- 示例集合：`docs/delivery/api/examples.md` 与 `docs/delivery/api/mock-data.json`
- 变更记录：`docs/delivery/api/api-changelog.md`
- 交付总览：`docs/delivery/FRONTEND_DELIVERY_READINESS.md`（持续更新）

## 6.2 最小接口集（MVP）

- `GET /health`
- `GET /catalog/chapters`
- `GET /topics`、`GET /topics/{topic_id}`
- `GET /problems`、`GET /problems/{problem_id}`
- `GET /search`、`POST /search`
- `GET /quality/summary`

注：如现网路径与上述命名存在差异，以“兼容映射表”方式交付，不强制一次性改路径。

## 7. 契约规范

## 7.1 OpenAPI 约束

- 使用 OpenAPI 3.x，声明统一 `servers`、`securitySchemes`、`schemas`
- 每个端点必须包含：用途、参数、返回示例、错误码、鉴权要求
- 统一分页字段与排序语义
- 统一时间、枚举、布尔、空值表示规范
- 明确所有响应统一返回 `trace_id`，并通过响应头返回 `X-Trace-Id`

## 7.2 错误模型

- 标准错误对象：`code`、`message`、`request_id`、`details`
- 错误码分层：鉴权类、参数类、资源类、系统类、限流类
- 所有 4xx/5xx 必须有示例与前端处理建议

## 7.3 版本管理

- 对外默认 `v1` 契约冻结窗口
- 破坏性变更仅允许通过 `v2` 发布
- 兼容性变更遵循“新增优先、删除延后、弃用声明”

## 8. 浏览器访问与安全

## 8.1 CORS 策略

- 明确允许来源（按环境白名单）
- 明确允许方法、请求头、暴露响应头、缓存时长
- 必须支持 `OPTIONS` 预检响应
- 必须给出“开发环境宽松策略”与“生产环境最小授权策略”两套模板

## 8.2 鉴权接入

- 延续现有 API Key 机制，补齐前端请求模板
- 明确 token/key 获取、轮换、失效与错误处理路径
- 区分开发密钥与生产密钥使用边界

## 9. 环境与部署

## 9.1 环境矩阵

- local：开发自测
- dev：团队联调
- staging：发布前验收
- prod：正式访问

每个环境需提供：Base URL、鉴权方式、可用接口范围、限流策略、数据刷新频率。

## 9.2 运行方式

- 本地：启动 API 服务后对本机前端开放
- 云端：在目标环境部署 API 服务并配置域名/网关后开放
- 结论：前端访问的是“运行中的服务地址”，不是底层数据库文件

## 10. 分阶段实施

## Phase A：目录对齐与契约骨架

- 盘点现有接口并生成 OpenAPI 初稿
- 输出字段字典、错误码字典、兼容映射表
- 在 `docs/delivery/api/` 建立交付文档骨架并落位

## Phase B：浏览器联调可用化

- 补齐 CORS 与预检处理
- 形成前端最小样例调用集合
- 打通 dev 环境基础联调

## Phase C：验收与发布协同

- 契约一致性校验纳入流程
- 完成联调回归、错误场景回归
- 建立变更公告与版本发布节奏

## 11. 风险与缓解

- 并行改动导致契约漂移：采用冻结窗口与契约校验门禁
- 字段语义不一致：建立字段字典与评审机制
- 跨域策略过宽：按环境白名单最小授权
- 联调环境不稳定：设置 dev/staging 双环境兜底
- 历史文档口径不一致：统一以 `artifacts/acceptance/report.md` 为最新口径

## 12. 验收标准

- 前端最小接口集全部可在 OpenAPI 查询到并成功调用
- 浏览器跨域请求在目标环境稳定通过
- 前端开发者可仅凭交付文档完成独立联调
- 契约变更具备版本、审计、回滚说明
- 与主线优化并行期间未发生阻塞性冲突
- 新增交付资产全部落位至 `docs/delivery/api/`

## 13. 产出清单

- Spec 文档（本文件）
- 分解任务清单（tasks.md）
- 验收检查清单（checklist.md）
- `docs/delivery/api/openapi.yaml`
- `docs/delivery/api/frontend-integration-guide.md`
- `docs/delivery/api/environment-matrix.md`
- `docs/delivery/api/examples.md`
- `docs/delivery/api/mock-data.json`
- `docs/delivery/api/api-changelog.md`
