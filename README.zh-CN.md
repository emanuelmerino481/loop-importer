# Research Project Importer

[English](README.md)

**用一条命令，把长期靠 IDE、脚本和服务器人工维护的科研项目转换成可审核的 Agent Harness 草案；不执行、不修改源项目。**

![科研项目只读导入并由人工逐题审核](docs/demo-flow.svg)

长期科研项目通常散落着配置、训练脚本、checkpoint、旧指标、GPU 日志和没有写下来的决策。Agent 可以盘点它们，但不能把文件名和历史结果直接升级为科研事实。本工具把观察到的证据、低置信度推断和必须由人决定的问题明确分开。

## 完整 Demo

仓库包含一个原创的典型半成品科研项目：两个不一致的 seed、没有冻结的主指标、来源不明的“最佳结果”、缺少利用率的 GPU 日志，以及必须脱敏的 `.env`。

**[查看导入前后完整 Demo →](examples/README.md)**

导入后会生成：

- [`project-manifest.yaml`](examples/generated-import-packet/project-manifest.yaml)：扫描范围和项目概况；
- [`artifact-registry.yaml`](examples/generated-import-packet/artifact-registry.yaml)：稳定证据 ID、受控 hash 和脱敏状态；
- [`task-dag.yaml`](examples/generated-import-packet/task-dag.yaml)：低置信度任务与依赖候选；
- [`review-session.yaml`](examples/generated-import-packet/review-session.yaml)：推荐答案、证据、人工裁决和问题依赖；
- [`import-report.html`](examples/generated-import-packet/import-report.html)：中文人工审核页面。

## 快速开始

```bash
git clone https://github.com/emanuelmerino481/research-project-importer.git
cd research-project-importer
python -m pip install -e .

research-project-import /path/to/existing-project \
  --project-id MY-PROJECT \
  --output /path/to/imports/MY-PROJECT

python skills/research-project-importer/scripts/validate_import.py \
  /path/to/imports/MY-PROJECT
```

## 人工审核方式

审核不是一次丢出一串问题。Agent 必须先检查证据候选，每次只展示一个问题和推荐答案，等待研究者选择确认、修正、拒绝推断或要求补证。所有必答项解决并得到人工批准前，状态保持 `DRAFT_HUMAN_REVIEW`，不得启动正式实验。

## 安全边界

- 不执行或修改源项目代码；
- 不跟随符号链接，不遍历 Git、虚拟环境、缓存、WandB 或 MLflow；
- 不读取或 hash 疑似秘密文件；
- 侦察阶段不 hash 大数据和 checkpoint；
- 清除 HTTP Git remote 中的账号、密码和 query；
- 拒绝把导入结果写进源项目内部。

它是项目侦察和人工审核工具，不是沙箱，也不自动证明实验正确。公开导入包前仍需检查其中的路径。

Demo 结构参考 [Cookiecutter Data Science](https://github.com/drivendataorg/cookiecutter-data-science) 等常见科研项目布局，但全部示例内容均为原创合成数据，不包含第三方科研结果。问答审核来源与采用边界见 [docs/SOURCES.md](docs/SOURCES.md)。

项目采用 [Apache-2.0](LICENSE)。参与贡献请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
