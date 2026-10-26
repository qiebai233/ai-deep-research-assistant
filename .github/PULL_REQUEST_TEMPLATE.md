# Pull Request

## 这个 PR 做了什么

<!-- 一句话说明改动；较大的改动请附背景与设计取舍 -->

## 关联 Issue

<!-- Closes #123 / Related #456；没有则写“无” -->

## 改动类型

- [ ] Bug 修复（不改变现有行为）
- [ ] 新功能
- [ ] 重构 / 性能优化（外部行为不变）
- [ ] 文档 / 示例
- [ ] CI / 构建 / 发布
- [ ] 其他（请在描述里说明）

## 影响范围

<!-- 涉及模块：CLI / Web UI / LLM / search / fetch / agent / report / config / docs -->

## 如何验证

<!-- 贴出你实际运行的命令与结果；reviewer 会照着复核 -->

```bash
python -m compileall -q src
ruff check src tests
python run_tests.py
```

离线功能验证：

```bash
deepresearch run "你的测试问题" --provider mock --depth quick
```

## 检查清单

- [ ] 没有新增运行时第三方依赖（仅 Python 标准库）
- [ ] 测试完全离线，没有真实联网调用
- [ ] 新增/变更行为有对应测试，`python run_tests.py` 全绿
- [ ] `ruff check src tests` 通过，行宽 ≤ 100
- [ ] 同步更新了文档（README / docs / .env.example，若涉及配置或命令）
- [ ] 未提交任何密钥、`.env`、`reports/`、`.deepresearch/` 等本地文件
- [ ] 没有在 PR 中修改已发布版本的 `CHANGELOG.md` 小节（改动记录写在 `Unreleased` 下）
- [ ] 若涉及用户可见行为变化，已在 PR 描述中说明迁移方式

## 截图 / 输出（可选）

<!-- UI 改动请附截图；报告改动请附生成 Markdown 的关键片段 -->
