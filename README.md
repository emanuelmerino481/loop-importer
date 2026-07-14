# Research Project Importer

把已经用 IDE、脚本和服务器人工维护的科研项目，只读转换为可审核的 Agent Harness 导入草案。它解决“项目在哪里、脚本依赖什么、哪些判断只是模型猜测、人工应该审什么”，但不会自动宣称实验正确。

## 关键原则

- 源项目只读：不运行脚本、不改文件、不跟随符号链接。
- 安全盘点：跳过 Git、虚拟环境、缓存、WandB 和 MLflow；秘密文件只登记脱敏元数据。
- 科研判断由人负责：指标、统计单位、数据版本、seed、baseline、阈值和结论都必须审核。
- 一次只审一个问题：先查看证据 ID，展示 Agent 推荐答案，等待人工确认、修正、拒绝或要求补证。
- 所有必答项解决前，状态始终是 `DRAFT_HUMAN_REVIEW`，不得启动正式实验。

## 安装与使用

```bash
python -m pip install -e .

research-project-import /path/to/existing-project \
  --project-id MY-PROJECT \
  --output /path/to/imports/MY-PROJECT

python skills/research-project-importer/scripts/validate_import.py \
  /path/to/imports/MY-PROJECT
```

输出包括：

- `project-manifest.yaml`：扫描范围、语言、Git 元数据和分类计数；
- `artifact-registry.yaml`：稳定 artifact ID、路径、大小与受控 hash；
- `task-dag.yaml`：低置信度的训练、推理、评估和报告候选；
- `open-questions.yaml` / `review-session.yaml`：推荐答案、证据、依赖和人工裁决；
- `bootstrap.md`：新会话冷启动入口；
- `import-summary.json` 与中文 `import-report.html`。

## Codex Skill

仓库内的 `skills/research-project-importer/` 可安装为 Codex Skill。它要求 Agent 逐题审核，不允许把文件名推断升级为科研事实，也不允许在人工放行前激活任务。

## 安全边界

请先在副本或只读挂载上试用。扫描器不会读取秘密文件内容，也会清除 Git HTTP remote 中的用户名、密码和 query；但文件路径本身仍可能包含项目敏感信息，公开报告前必须人工检查。大文件和 checkpoint 不在侦察阶段计算 hash。

安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。

## 致谢与来源

人工问答审核工作流受到 [mattpocock/skills](https://github.com/mattpocock/skills) 中 `grilling`、`grill-me` 和 `grill-with-docs` 的启发：一次一题、先检查事实、提供推荐答案并等待人类决策。上游采用 MIT License；本仓库未复制其实现代码，而是在科研导入场景中增加证据 ID、裁决字段、依赖与激活门。固定版本和采用边界见 [docs/SOURCES.md](docs/SOURCES.md)。

## License

Apache-2.0。
