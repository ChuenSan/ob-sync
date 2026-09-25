---
title: "Chat Completions与Responses调用方式对比"
saved_at: "2026-09-25 10:21:42 CST"
source: "抖音"
original_title: "Agent 系列课程之大模型调用 Chat Com..."
author: "马安强 AI 普及"
share_code: "https://v.douyin.com/4CDEvxmM7xc/"
category: "智能体"
tags:
  - "领域-智能体"
  - "领域-AI编程"
  - "内容形式-知识科普"
  - "价值类型-技术理解"
  - "接口-Chat Completions"
  - "接口-Responses"
  - "方法-状态管理"
  - "概念-工具调用"
---

# 速览

## 一句话主旨

Chat Completions 以 `messages` 为核心，适合简单问答；Responses 以 `input` 和 `output` 组织更丰富的消息、工具调用与推理结果，面向复杂 Agent 任务，并通过 `previous_response_id` 或手动拼接上下文实现多轮状态管理。

## 核心要点

- Chat Completions 和 Responses 是 OpenAI 提供的两种大模型调用方式，前者主要面向简单问答，后者更适合复杂的 Agent 场景。
- Chat Completions 的请求体使用 `messages` 字段，通过 system、user、assistant 角色组织对话历史；Responses 使用 `input`，可以容纳消息、工具调用等多种 item。
- Chat Completions 的响应主要围绕 `message` 返回文本回答；Responses 返回 `output` 数组，可包含 message、tool_calls、reasoning 等多种结果类型。
- Responses 在多轮 Agent 调用中的关键优势是状态管理：模型调用工具后，工具结果可以继续与之前的推理过程关联。
- Responses 支持通过 `previous_response_id` 让服务端自动关联上一轮状态，也支持将上一轮 reasoning 和工具结果作为新输入来手动维护上下文。
- 选择方案时，简单问答可使用接口更直接的 Chat Completions；Agent 开发更适合使用专为复杂任务设计的 Responses。
- 选择调用方式和组织上下文仍需要开发者根据任务判断，不能完全交给 AI 生成代码来决定。

# 视频原文

大模型调用方式解析：Chat Completions vs. Responses

视频讲解了 OpenAI 提供的两种大模型调用方式：Chat Completions 和 Responses。核心区别在于，Chat Completions 主要用于简单的问答，而 Responses 是为复杂的 Agent 场景设计的，能更好地处理工具调用、多轮推理和状态管理。

两种调用方式的核心差异

从请求体和响应体的结构可以直观地看出两者的设计目标不同。

对比维度 Chat Completions Responses
请求体 使用 `messages` 字段，包含 system, user, assistant 角色的对话历史。 使用 `input` 字段，可包含消息、工具调用等多种类型的 item。
响应体 围绕 `message` 组织，主要返回文本回答。 返回 `output` 数组，可包含 message、tool_calls、reasoning 等多种类型的结果。
核心用途 简单的问答对话。 复杂的 Agent 任务，如多轮工具调用、推理链。

Responses 的关键优势：状态管理

在开发 Agent 时，一个核心挑战是如何在多轮调用中保持推理状态。例如，模型决定调用工具后，工具返回的结果需要与之前的推理过程关联起来。

Responses 提供了两种方式来解决这个问题：

自动关联
通过传入 `previous_response_id`，让服务端自动帮你关联上一轮的状态。

手动维护
将上一轮的推理过程（reasoning）和工具结果一起作为新的输入，手动构建上下文。

如何选择？

虽然 Chat Completions 也支持工具调用，但在不同场景下，选择更合适的方案能让开发更高效。

场景 推荐方案 原因
简单问答 Chat Completions 接口简单，直接返回文本，满足基本需求。
Agent 开发 Responses 专为复杂任务设计，能更好地处理工具调用、多轮推理和状态衔接。

总结

💡 理解这两种调用方式的底层结构，是规划 Agent 上下文、实现复杂逻辑的基础。虽然 AI 可以辅助生成代码，但选择合适的方案、决定如何组织上下文，仍需开发者自己判断。
