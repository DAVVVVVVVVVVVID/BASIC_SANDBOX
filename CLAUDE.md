# CLAUDE.md

## 项目背景

这是一款基于2D方块的网页游戏。

* 前端：React + TypeScript + Phaser
* 后端：Python + FastAPI
* 架构：前端/后端分离

## 核心规则（必须遵守）

后端权限:

* 后端是唯一可信的数据源
* 所有游戏逻辑都必须在后端实现

前端严禁：

* 判断移动是否有效
* 直接修改游戏状态
* 解决交互问题

## API 管理规则（必须遵守）

* API 标准化文件：`./docs/api-spec.md`
* 每次对沙盒 API 进行任何增删改（新增接口、修改请求/响应结构、新增 action type），**必须同步更新** `./docs/api-spec.md`
* agent 调用沙盒的所有接口均以此文件为准

## 文档索引
* 项目总体说明：./docs/SRS.md
* 数据模型：./docs/data-models.md
* API 规范：./docs/api-spec.md
* 坐标系：./docs/coordinate.md
* 架构：./docs/architecture.md
* 开发里程碑：./docs/milestones.md
* 前端设计文档：./docs/frontend-design.md
* 游戏机制说明：./docs/game-mechanics.md
