-- 数据库迁移：统一术语（halfday → period）
-- 执行日期：2025-11-07
-- 描述：重命名表名、字段名，统一使用 period 术语

-- ===============================================
-- 步骤 1：重命名表（topic_halfday_heat → topic_period_heat）
-- ===============================================
ALTER TABLE topic_halfday_heat RENAME TO topic_period_heat;

-- 更新表注释
COMMENT ON TABLE topic_period_heat IS '主题归并周期热度记录表';

-- ===============================================
-- 步骤 2：重命名 source_items 表的字段
-- ===============================================

-- 重命名 halfday_merge_group_id → period_merge_group_id
ALTER TABLE source_items 
RENAME COLUMN halfday_merge_group_id TO period_merge_group_id;

-- 重命名 halfday_period → period
ALTER TABLE source_items 
RENAME COLUMN halfday_period TO period;

-- 更新字段注释
COMMENT ON COLUMN source_items.period_merge_group_id IS '归并组ID';
COMMENT ON COLUMN source_items.period IS '归并时段（如2025-10-29_AM/PM/EVE）';
COMMENT ON COLUMN source_items.occurrence_count IS '归并周期内出现次数';
COMMENT ON COLUMN source_items.heat_normalized IS '归并周期内归一化热度（0-1）';

-- ===============================================
-- 步骤 3：重命名索引
-- ===============================================

-- 重命名 source_items 表的索引
ALTER INDEX idx_halfday_period_status RENAME TO idx_period_status;
ALTER INDEX idx_merge_group RENAME TO idx_merge_group;  -- 保持不变，但重新确认

-- ===============================================
-- 步骤 4：更新 merge_status 枚举值（可选）
-- ===============================================

-- 将 pending_halfday_merge 改为 pending_event_merge
UPDATE source_items 
SET merge_status = 'pending_event_merge'
WHERE merge_status = 'pending_halfday_merge';

-- ===============================================
-- 步骤 5：验证迁移结果
-- ===============================================

-- 检查表是否存在
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_name = 'topic_period_heat'
);

-- 检查字段是否存在
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'source_items' 
AND column_name IN ('period', 'period_merge_group_id');

-- 检查数据完整性
SELECT 
    period, 
    COUNT(*) as count,
    MIN(fetched_at) as min_time,
    MAX(fetched_at) as max_time
FROM source_items 
WHERE period IS NOT NULL
GROUP BY period
ORDER BY period;

-- ===============================================
-- 回滚脚本（如果需要）
-- ===============================================
/*
-- 回滚步骤（按相反顺序执行）

-- 恢复 merge_status
UPDATE source_items 
SET merge_status = 'pending_halfday_merge'
WHERE merge_status = 'pending_event_merge';

-- 重命名字段回原名
ALTER TABLE source_items RENAME COLUMN period TO halfday_period;
ALTER TABLE source_items RENAME COLUMN period_merge_group_id TO halfday_merge_group_id;

-- 重命名索引回原名
ALTER INDEX idx_period_status RENAME TO idx_halfday_period_status;

-- 重命名表回原名
ALTER TABLE topic_period_heat RENAME TO topic_halfday_heat;

-- 恢复表注释
COMMENT ON TABLE topic_halfday_heat IS '主题半日热度记录表';
*/

