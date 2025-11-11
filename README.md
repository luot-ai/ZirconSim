# ZirconSim

本项目是在ChiselTest停止更新后，为Zircon-2024处理器设计的C++仿真环境。其性能相比ChiselTest提升了约50%，并无需复杂的Scala库支持。

## 使用方法

请将本项目放到Zircon-2024的根目录下。执行如下命令可以构建项目：

```bash
make 
```
## profiling

进入`RV-Software/XX` 运行
```bash
make run
```
会得到输出`ZirconSim/profiling/XX-riscv32/base.log`

   
然后进入`ZirconSim` 运行
```bash
python3 trace.py XX-riscv32
```
`ZirconSim/profiling/XX-riscv32/`下会生成`blkinfo`和`blkview`，后者可使用 perfetto UI [网页版](https://www.ui.perfetto.dev/) 打开
