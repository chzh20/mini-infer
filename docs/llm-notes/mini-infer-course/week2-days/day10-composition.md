# Day 10：Composition 优先于继承 — 每日学习教程

> 所属项目：`mini-infer`
> 前置基础：Day 9 `Protocol` / 依赖反转、Day 4 `ModelSession` 资源管理
> 学员画像：EDA 工程师，C++ 系统背景（对组合/继承、构造函数注入天然熟悉）
> 设计依据：`roadmap.md` Day 10「拆分策略、状态和生命周期」

---

## 一、学习目标（当天要掌握的核心知识点）

1. 区分 **is-a（继承）** 与 **has-a（组合）**，识别「继承层级膨胀」的征兆。
2. 理解 **mixin** 的适用边界（横向能力复用，而非业务层级）。
3. 掌握 **委托（delegation）** 与 **依赖注入（DI）**：把组件通过构造函数传入，而非在类内部 `new`。
4. 理解 **组合根（composition root）**：对象图在一个明确的位置组装。
5. 在 `mini-infer` 中把 `InferenceEngine` 重构为「组合多个可替换组件」，并能替换任意组件做测试。

---

## 二、时间分配（建议总时长 ≈ 2 小时）


| 环节     | 内容                                       | 时长     |
| ------ | ---------------------------------------- | ------ |
| 开场     | 目标 + 衔接 Day 9（协议已就绪，今天组合它们）              | 3 min  |
| 学习内容 1 | is-a vs has-a；继承膨胀征兆                     | 12 min |
| 学习内容 2 | mixin 边界；委托                              | 10 min |
| 学习内容 3 | 依赖注入（DI）与组合根                             | 15 min |
| 学习内容 4 | 反例演示：`GreedyHuggingFaceLoggedEngine`     | 8 min  |
| 实践任务   | 重构 `InferenceEngine` 为组合结构 + 构造注入 + 测试替换 | 45 min |
| 复习与收尾  | 自测 + 衔接 Day 11                           | 7 min  |


---



## 三、学习内容



### 3.1 is-a 与 has-a；继承膨胀征兆

继承表达「是一种（is-a）」，组合表达「有一个（has-a）」。推理引擎**不是**「一种」tokenizer，而是「**拥有**」一个 tokenizer。强行用继承会得到怪物类：

```python
# ❌ 继承膨胀：每多一个变化维度，子类数指数爆炸
class GreedyHuggingFaceLoggedEngine(BaseEngine): ...
class TopKWhitespaceEngine(BaseEngine): ...
# 变化维度 = {采样算法} × {tokenizer} × {是否记录} → 组合爆炸
```

**识别征兆**（看到就该警惕）：

- 类名包含 `And` / 多个形容词拼接（`GreedyLogged...`）。
- 子类只为覆写一个方法、其余全继承。
- 想加一个新行为就要新建一个子类。



### 3.2 mixin 的边界；委托

- **mixin**：给多个类附加**横向能力**（如「可日志化」「可缓存」），本身不代表业务实体。仅当能力正交且需多继承时才用；滥用 mixin 会回到菱形继承泥潭。
- **委托（delegation）**：对象不自己实现某能力，而是把调用转给内部持有的组件。这正是组合的核心机制。

```python
class InferenceEngine:
    def __init__(self, tokenizer: Tokenizer, model: Model, sampler: Sampler):
        self._tokenizer = tokenizer   # 委托给内部组件
    def generate(self, prompt):
        ids = self._tokenizer.encode(prompt)   # 委托
        ...
```



### 3.3 依赖注入与组合根

这段话描述的是现代软件设计中的两个核心概念：**依赖注入（Dependency Injection, DI）** 和 **组合根（Composition Root）**。它们一起解决的问题是：

> **对象如何获得它需要的依赖，以及这些依赖应该在哪里创建。**

---



#### 什么是依赖（Dependency）

先看一个简单例子：

```python
class Tokenizer:

 def encode(self, text):

 ...
```

一个推理引擎需要使用 Tokenizer：

```python
class LLMEngine:

 def init(self):

 self.tokenizer = Tokenizer()

 def generate(self, text):

 ids = self.tokenizer.encode(text)

 ...
```

这里：Tokenizer 就是 `LLMEngine` 的依赖。

---



#### 2. 什么是依赖注入（DI）

问题在于：self.tokenizer = Tokenizer()

依赖是在类内部创建的。

这叫：Hard-coded dependency 硬编码依赖

类和具体实现绑死了。

---



#### 改成依赖注入

让外部传进来：

```python

class LLMEngine:

 def init(self, tokenizer):

 self.tokenizer = tokenizer

 def generate(self, text):

 ids = self.tokenizer.encode(text)
```

使用时：

```python
tokenizer = Tokenizer()

engine = LLMEngine(tokenizer)
```

这里：tokenizer是从外部注入进去的。

这就叫：
Dependency Injection
即：

> 对象不负责创建依赖，只负责使用依赖。

---



#### 3. 为什么这样更好

好处1：便于测试

原来的代码：

```python
class LLMEngine:

 def init(self):

 self.tokenizer = Tokenizer()

```

测试时一定会使用真 Tokenizer。

有时：

```python
Tokenizer

↓

加载词表

↓

读文件

↓

初始化很慢
```

测试困难。

---

现在：

```python
class FakeTokenizer:

 def encode(self, text):

 return [1, 2, 3]
```

测试时：

```python
engine = LLMEngine(FakeTokenizer())
```

整个测试：不读文件，不加载词表, 不依赖真实环境

只测：LLMEngine 的逻辑
这叫：Mock/Fake Testing

---

好处2：实现可替换

例如未来有多个 Tokenizer：

```python

SentencePieceTokenizer

BPETokenizer

HFTokenizer
```

业务代码：

```python
class LLMEngine:

 def init(self, tokenizer):

 self.tokenizer = tokenizer

```

完全不用改。

运行时决定：

engine = LLMEngine(BPETokenizer())

或者：

engine = LLMEngine(HFTokenizer())

即可。

---

好处3：减少耦合

如果写成：

```python
self.tokenizer = HFTokenizer()
```

则：

```python
LLMEngine

 ↓

HFTokenizer
```

强绑定。

如果以后：

```python
HFTokenizer

↓

改名

↓

删除

↓

迁移
```

`LLMEngine` 必须修改。

DI 后：

```python
LLMEngine

 ↓

Tokenizer接口
```

不关心具体实现。这叫：依赖抽象，不依赖具体实现

也是 SOLID 的 DIP（Dependency Inversion Principle）。

---



#### 4. Constructor Injection（构造函数注入）

最常见形式：

```python

class Engine:

 def init(self, tokenizer):

 self.tokenizer = tokenizer
```

依赖创建对象时传入。

优点：

对象创建完成即合法

依赖不能为空

推荐优先使用。

---



#### 5. Setter Injection（Setter 注入）

另一种方式：

```python
class Engine:

 def set_tokenizer(self, tokenizer):

 self.tokenizer = tokenizer
```

使用：

```python
engine = Engine()

engine.set_tokenizer(tokenizer)
```

优点：运行时可以动态替换

缺点：对象可能处于半初始化状态

例如：

```python
engine = Engine()

engine.generate(...)
```

可能报错。

因此通常：

构造函数注入 > Setter 注入

---



#### 6. 什么是组合根（Composition Root）

很多人学 DI 后会产生新问题：

既然类不自己 new，那谁来 new？

答案：Composition Root,组合根

例如：

```python
tokenizer = HFTokenizer()

model = LlamaModel()

scheduler = Scheduler()

engine = LLMEngine(

 tokenizer,

 model,

 scheduler

)
```

这些：new ...都放在一个地方。

例如：

```python

main()

build_engine()

Factory

```



# 7. 一个错误示例

如果每个类都自己创建依赖：

```python
class Engine:

 def init(self):

 self.tokenizer = Tokenizer()





class Tokenizer:

 def init(self):

 self.vocab = Vocabulary()





class Vocabulary:

 def init(self):

 self.loader = FileLoader()

```

对象图变成：

```python
Engine

 └── Tokenizer

 └── Vocabulary

 └── FileLoader
```

依赖关系藏在代码各处。你根本不知道 Engine到底会创建多少对象.这就是：Hidden Dependency,隐藏依赖.

---



#### 8. 使用组合根后的结构

```python
def build_engine():

 loader = FileLoader()

 vocab = Vocabulary(loader)

 tokenizer = Tokenizer(vocab)

 model = LlamaModel()

 return LLMEngine(

 tokenizer,

 model

 )
```

所有 `new` 集中在这里。

对象图一眼可见：

```python
build_engine()

│

├── FileLoader

├── Vocabulary

├── Tokenizer

├── LlamaModel

└── LLMEngine
```

这就是：Composition Root

---



# 9. 在 mini-infer/vLLM 中的典型体现

例如不要这样：

```python

class Engine:

 def init(self):

 self.tokenizer = HFTokenizer()

 self.sampler = Sampler()

 self.cache = KVCache()
```

而是：

```python
class Engine:

 def init(

 self,

 tokenizer,

 sampler,

 cache,

 ):

 self.tokenizer = tokenizer

 self.sampler = sampler

 self.cache = cache

```

然后：

```python
def build_engine(cfg):

 tokenizer = HFTokenizer(cfg)

 sampler = TopPSampler(cfg)

 cache = PagedKVCache(cfg)

 return Engine(

 tokenizer,

 sampler,

 cache,

 )

```

这样：

- Engine 只负责推理逻辑
- build_engine 负责装配对象
- 测试可替换 FakeTokenizer
- 运行时可替换不同 Cache/Sampler
- 所有依赖关系集中可见

这正是大型项目（vLLM、Spring、[ASP.NET](http://ASP.NET) Core、Uber Fx、Google Guice 等）普遍采用的架构思想：

DI 解决：

 “依赖从哪里来”

Composition Root 解决：

 “依赖在哪里创建”

组合根 = 唯一允许大量 new 的地方

业务类 = 只声明依赖，不创建依赖

```python
# 组合根：对象图在此一次性组装（Day 12 的 Factory 会接管这里）
def build_engine(config) -> InferenceEngine:
    tokenizer = WhitespaceTokenizer.from_file(config.vocab)
    model = TinyModel(config.hidden_size)
    sampler = GreedySampler()
    scheduler = Scheduler(config.max_batch)
    metrics = LoggingMetricsSink()
    return InferenceEngine(tokenizer, model, sampler, scheduler, metrics)
```

> C++类比：这正是一直在做的——依赖通过构造函数注入（构造函数注入是 C++ 里最普通的 DI 形式），对象图在 `main` 里组装。Python 只是少了模板样板。



### 3.4 反例现场演示

导师先写一个 `GreedyHuggingFaceLoggedEngine(BaseEngine)` 让学员看到：一旦要加 `TopK` + `Whitespace` + `Silent`，需要 `2×2×2=8` 个子类。然后现场拆成 4 个独立组件 + 组合根，子类数归零。痛苦感强化「组合优于继承」。

---



## 四、实践任务

**任务 1（基础）— 定义组件协议（复用 Day 9）**

- 确认 `protocols.py` 已有 `Tokenizer`、`Sampler`、`Model`、`Scheduler` 协议（今天新增 `MetricsSink` 协议：`record(meta: GenerationMeta) -> None`）。

**任务 2（进阶）— 重构** `InferenceEngine` **为组合结构**

- 把 `engine/engine.py` 改成：

```python
class InferenceEngine:
    def __init__(self, *, tokenizer: Tokenizer, model: Model,
                 sampler: Sampler, scheduler: Scheduler,
                 metrics: MetricsSink) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._sampler = sampler
        self._scheduler = scheduler
        self._metrics = metrics
```

- `generate` 内部通过委托调用各组件。**禁止** `from .tokenizer.whitespace import ...` 这类具体导入。

**任务 3（进阶）— 组合 root + 测试替换**

- 在 `engine/__init__.py` 或 `cli.py` 加一个 `build_engine(config)` 作为组合根。
- 写测试：用 `FakeTokenizer` + `FakeModel` + `GreedySampler` 注入，验证 `generate` 跑通（呼应 Day 6 的 fake 优先）。

**检查点 / 预期输出**

```python
eng = InferenceEngine(
    tokenizer=FakeTokenizer(), model=FakeModel(),
    sampler=GreedySampler(), scheduler=Scheduler(8), metrics=LoggingMetricsSink())
out = eng.generate("hello")
assert isinstance(eng.tokenizer, FakeTokenizer)   # 注入了替身，没用具体类
```

断言：Engine 不持有具体组件类型；测试用 fake 替换全部组件且 `pytest` 通过；项目里无 `GreedyHuggingFaceLoggedEngine` 式膨胀类。

---



## 五、学习重点（难点与关键点）

- **能组合就别继承**：口诀——「**优先 has-a，仅在『真的是同一种东西』时才 is-a**」。推理引擎不是 tokenizer，所以它 has-a tokenizer。
- **组合根的唯一性**：对象图只在一处组装。若发现 `InferenceEngine` 内部又 `new` 了 `Scheduler`，说明组合根漏了。
- **DI 让测试免费**：因为依赖由外部注入，测试换 fake 几乎零成本——这是 Day 6「测行为」能成立的工程前提。
- `ModelSession` **的位置**：Day 4 的 `ModelSession` 资源管理器应作为 `Model` 组件的持有者被注入 Engine，而非 Engine 自己管理 GPU 生命周期（呼应 RAII 思想）。

---



## 六、复习与巩固

- **衔接 Day 9**：今天组合的就是 Day 9 定义的 `Tokenizer`/`Sampler` 等协议。复习——若某组件不是 Protocol 而是具体类，`InferenceEngine` 的构造参数类型就会退化成具体依赖，依赖反转被破坏。
- **衔接 Day 4**：`ModelSession`（上下文管理器）是「资源管理」的实现，今天它作为 `Model` 组件被注入。复习 `with ModelSession(...) as s` 的生命周期如何与组合结构共存。
- **三道题自测**：
  1. `InferenceEngine` 和 `Tokenizer` 之间是 is-a 还是 has-a？据此该用继承还是组合？
  2. 组合根放哪里最合适？为什么不让 `InferenceEngine.__init__` 内部直接 `Tokenizer()`？
  3. 给 `InferenceEngine` 加「记录耗时」能力，用 mixin 还是注入 `MetricsSink`？为什么？
- **预告 Day 11**：明天落地第一个可替换组件——`Sampler` 系列（greedy / top-k / temperature），正是组合结构的第一个「即插即用」受益者。

---



## 七、延伸阅读

- 《Refactoring》（Martin Fowler）：「Replace Inheritance with Delegation」「Extract Interface」。
- 《Effective C++》/ 《Modern C++ Design》：构造函数注入、组合优于继承的母语级论据。
- 衔接：Day 11 Strategy（Sampler 即组合组件）、Day 12 Factory（组合根的自动化）、Day 14 DI 解决全局状态。

