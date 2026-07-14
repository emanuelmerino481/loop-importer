<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/hero-light.svg">
  <img alt="Loop Importer——证据优先，人工批准" src="docs/hero-light.svg">
</picture>

[English](README.md)

## 导入旧项目，不导入它的含糊判断

**用一条命令，把长期靠 IDE、脚本和服务器人工维护的科研项目转换成可审核的 Agent Harness 草案；不执行、不修改源项目。**

![科研项目只读导入并由人工逐题审核](docs/demo-flow.svg)

长期科研项目通常散落着配置、训练脚本、checkpoint、旧指标、GPU 日志和没有写下来的决策。Agent 可以盘点它们，但不能把文件名和历史结果直接升级为科研事实。本工具把观察到的证据、低置信度推断和必须由人决定的问题明确分开。

## 💌 写给来到这里的你

嗨，欢迎来到这里！👋

我现在大一，也才刚刚开始接触 AI 编程、Agent 和 Harness。很多东西还在边学边做，并不是什么经验丰富的大佬。最开始，我只是用 Trae 一步一步做自己已经开起来的项目。项目越做越长，脚本、配置、实验结果、GPU 记录，还有各种“以后再整理”的想法，也就慢慢散得到处都是。🌱💻

我当时很想让项目真正跑成一个 Loop：Agent 能读懂当前项目，做一次有边界的修改，运行或者验证，保存证据，给我汇报，然后再继续下一轮。听起来好像挺自然，对吧？🔁🧪

但真的开始做以后，我发现：想把一个**已经开工、已经有历史包袱的项目**接进 Loop，貌似比从零搭一个漂亮 Demo 难多了。模型找到了 `train.py`，不代表它知道哪个才是正式入口；看见最大的 accuracy，不代表它知道主指标；读过文件，也不等于真的理解实验。对话一断、上下文一丢，很多之前讲清楚的东西又得重新来一遍。😵‍💫

所以我就一点一点弄出了这个东西。它比较对口的人，可能不是所有开发者，而是像我一样的这部分人：项目已经在跑了，文件也已经有点乱了，不太可能全部推倒重来，但又真的想把 Agent、Harness 和循环工作流接进来。也包括做课程、科研、个人实验，或者维护长期脚本的同学。🧰🤖📚

这是我第一次把这样的东西公开出来，现在肯定还不完美。如果它碰巧也解决了你的问题，欢迎拿真实项目试试看；哪里不对就提 Issue，觉得我的理解有问题也请直接纠正我。能收到一个 Star 当然会很开心 ⭐，但如果它真的帮某个旧项目顺利走进 Loop，那就更酷了。❤️

也很感谢我的本科生导师一路上的帮助。他也很欢迎对 **生物 + AI** 交叉方向感兴趣的同学来交流。🧬🤖 如果你真的对这个方向感到好奇，想进一步了解或者聊聊，可以通过邮箱联系他：[dacheng2023@126.com](mailto:dacheng2023@126.com)。📮

谢谢你愿意看到这里，也欢迎和我一起把它慢慢做得更好！🚀

— [@emanuelmerino481](https://github.com/emanuelmerino481)

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
git clone https://github.com/emanuelmerino481/loop-importer.git
cd loop-importer
python -m pip install -e .

loop-import /path/to/existing-project \
  --project-id MY-PROJECT \
  --output /path/to/imports/MY-PROJECT

python skills/loop-importer/scripts/validate_import.py \
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
