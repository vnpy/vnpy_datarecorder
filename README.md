# vn.py框架的行情录制模块

<p align="center">
  <img src ="https://vnpy.oss-cn-shanghai.aliyuncs.com/vnpy-logo.png"/>
</p>

<p align="center">
    <img src ="https://img.shields.io/badge/version-1.0.2-blueviolet.svg"/>
    <img src ="https://img.shields.io/badge/platform-windows|linux|macos-yellow.svg"/>
    <img src ="https://img.shields.io/badge/python-3.7|3.8|3.9|3.10-blue.svg" />
    <img src ="https://img.shields.io/github/license/vnpy/vnpy.svg?color=orange"/>
</p>

## 说明

DataRecorder是用于实时行情记录的模块，用户可以利用该模块记录实时Tick数据和K线数据，并自动写入保存到数据库中。

记录的数据可以通过DataManager模块查看，也可以用于CtaBacktester的历史回测，以及CtaStrategy、PortfolioStrategy等策略的实盘初始化。

## 安装

安装需要基于3.0.0版本以上的[VN Studio](https://www.vnpy.com)。

直接使用pip命令：

```
pip install vnpy_datarecorder
```

下载解压后在cmd中运行

```
pip install -e .
```
