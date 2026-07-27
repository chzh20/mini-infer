# Benchmarks

W3 开始在这里加入可复现 benchmark。每条结果必须记录：

- CPU/GPU 型号与数量、拓扑；
- Python、框架、CUDA、驱动和代码 commit；
- batch、输入/输出长度、dtype；
- warm-up、重复次数和误差；
- TTFT、TPOT、throughput、峰值内存。

在实现真实模型前不发布没有意义的性能数字。

