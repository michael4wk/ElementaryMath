# 质量指标字典（评审版）

## 1. 指标口径

- `answer_analysis_consistency_rate_pct`
  - 定义：题干-答案-解析三者一致且答案与解析均存在的问题占比
  - 计算：`answer_analysis_consistent / problem_total * 100`
  - 阈值（staging硬门禁）：`>= 92`

- `empty_analysis_rate_pct`
  - 定义：解析步骤为空的问题占比
  - 计算：`empty_analysis_count / problem_total * 100`
  - 阈值（staging硬门禁）：`<= 8`

- `missing_common_mistakes_rate_pct`
  - 定义：主题对象中易错点字段缺失占比
  - 计算：`missing_common_mistakes_count / topic_total * 100`
  - 阈值（staging硬门禁）：`<= 15`

- `missing_grade_band_rate_pct`
  - 定义：题目年级字段缺失占比
  - 计算：`missing_grade_band_count / problem_total * 100`
  - 阈值（staging软门禁）：`<= 10`

- `missing_difficulty_rate_pct`
  - 定义：题目难度字段缺失占比
  - 计算：`missing_difficulty_count / problem_total * 100`
  - 阈值（staging软门禁）：`<= 3`

- `missing_learning_objectives_rate_pct`
  - 定义：主题学习目标字段缺失占比
  - 计算：`missing_learning_objectives_count / topic_total * 100`
  - 阈值（staging软门禁）：`<= 10`

- `source_ref_coverage_pct`
  - 定义：结构化对象中包含可追溯来源引用的占比
  - 计算：`source_ref_ready_count / total_objects * 100`
  - 阈值（prod硬门禁）：`>= 99`

- `semantic_consistency_confidence_avg_pct`
  - 定义：语义一致性二检置信度均值
  - 计算：问题级语义重叠置信度平均值
  - 运营阈值：`>= 45`（低于阈值触发告警）

## 2. 当前基线与最新值

- 初始基线（阶段起点）：
  - 一致率：79.51
  - 解析缺失率：19.26
  - 易错点缺失率：35.75

- 当前值（最新报告）：
  - 一致率：92.48
  - 解析缺失率：6.29
  - 易错点缺失率：0.0
  - source_ref覆盖率：100.0

## 3. 门禁等级

- 硬门禁：不达标直接阻断发布
- 软门禁：不达标发布可继续，但生成告警与整改工单
- 回退门禁：关键指标较上一周期下降超过阈值时触发阻断
