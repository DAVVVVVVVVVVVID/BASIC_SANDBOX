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

## 文档索引
* 项目总体说明：./docs/SRS.md
* 数据模型：./docs/data-models.md
* API 规范：./docs/api-spec.md
* 坐标系：./docs/coordinate.md
* 架构：./docs/architecture.md
* 开发里程碑：./docs/milestones.md
* 前端设计文档：./docs/frontend-design.md
* 游戏机制说明：./docs/game-mechanics.md
