# Import boundaries

依赖方向必须保持单向：

```text
CLI / examples
      ↓
engine ─────────→ protocols ←──── tokenizer / sampling / model
  ↓                   ↓
request ─────────→ config
  └────────────────→ exceptions
```

规则：

1. `config`、`exceptions` 和领域类型不依赖具体实现。
2. `protocols` 只定义跨模块契约；不创建组件。
3. `engine` 只依赖协议，通过构造函数注入实现。
4. tokenizer、sampler、model 彼此不导入。
5. 第三方库只允许出现在 adapter/backend 模块，外部类型不能进入公共 API。
6. `mini_infer.__init__` 是稳定 API 门面，内部 helper 不从这里导出。
7. 模块导入时不加载模型、不分配 GPU、不配置 root logger。

后续加入 PyTorch/C++/CUDA 时，依赖应继续指向 `Model`/backend contract，而不是让
Engine 感知 tensor backend、设备或 kernel 细节。

