# VeighNa框架的行情录制模块

<p align="center">
  <img src ="https://vnpy.oss-cn-shanghai.aliyuncs.com/vnpy-logo.png"/>
</p>

<p align="center">
    <img src ="https://img.shields.io/badge/version-1.1.1-blueviolet.svg"/>
    <img src ="https://img.shields.io/badge/platform-windows|linux|macos-yellow.svg"/>
    <img src ="https://img.shields.io/badge/python-3.10|3.11|3.12|3.13-blue.svg" />
    <img src ="https://img.shields.io/github/license/vnpy/vnpy.svg?color=orange"/>
</p>

## 说明

DataRecorder是用于实时行情记录的模块，用户可以利用该模块记录实时Tick数据和K线数据，并自动写入保存到数据库中。

记录的数据可以通过DataManager模块查看，也可以用于CtaBacktester的历史回测，以及CtaStrategy、PortfolioStrategy等策略的实盘初始化。

## 安装

安装环境推荐基于4.0.0版本以上的【[**VeighNa Studio**](https://www.vnpy.com)】。

直接使用pip命令：

```
pip install vnpy_datarecorder
```


或者下载源代码后，解压后在cmd中运行：

```
pip install .
```
