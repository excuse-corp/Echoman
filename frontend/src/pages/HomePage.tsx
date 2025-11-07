import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { CategoryEchoStat } from "../types";
import { dataSources, getCategoryEchoStats } from "../services/api";
import { ThemeToggle } from "../components/ThemeToggle";

const heroPhrases = [
  "一件事从发生到过去，他会持续多久？",
];

const CATEGORY_META: Record<
  "entertainment" | "current_affairs" | "sports_esports",
  { label: string; icon: string; tone: string }
> = {
  entertainment: { label: "娱乐八卦类事件", icon: "🎬", tone: "category-icon-entertainment" },
  current_affairs: { label: "社会时事类事件", icon: "📰", tone: "category-icon-society" },
  sports_esports: { label: "体育电竞类事件", icon: "🏆", tone: "category-icon-sports" },
};

const CATEGORY_ORDER: Array<keyof typeof CATEGORY_META> = [
  "entertainment",
  "current_affairs",
  "sports_esports",
];

function formatHoursToDayHour(totalHours: number) {
  if (!Number.isFinite(totalHours)) return "—";
  const rounded = Math.max(0, Math.round(totalHours));
  const days = Math.floor(rounded / 24);
  const hours = rounded - days * 24;
  
  // 不超过1天的情况只显示小时
  if (days === 0) {
    return `${hours}小时`;
  }
  
  return `${days}天${hours}小时`;
}

export function HomePage() {
  const [categoryStats, setCategoryStats] = useState<CategoryEchoStat[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    getCategoryEchoStats().then(({ items }) => {
      if (cancelled) return;
      setCategoryStats(items.slice(0, 3));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const headline = useMemo(() => heroPhrases[0], []);
  const [headlineLeading, headlineTrailing] = useMemo(() => {
    const parts = headline.split("，");
    if (parts.length > 1) {
      return [`${parts[0]}，`, parts.slice(1).join("，")];
    }
    return [headline, ""];
  }, [headline]);

  const orderedStats = useMemo(() => {
    const statsMap = new Map(categoryStats.map((stat) => [stat.category, stat]));

    return CATEGORY_ORDER.map((categoryKey) => {
      const meta = CATEGORY_META[categoryKey];
      const stat = statsMap.get(categoryKey);

      const displayValue = (value: number | undefined) => {
        if (!stat || value === undefined) {
          return "—";
        }
        if (value < 1) {
          return "<1小时";
        }
        return formatHoursToDayHour(value);
      };

      // 事件数量显示
      const displayCount = (value: number | undefined) => {
        if (!stat || value === undefined) {
          return "—";
        }
        return `${value}个`;
      };

      return {
        key: categoryKey,
        label: meta.label,
        icon: meta.icon,
        tone: meta.tone,
        average: displayValue(stat?.avg_length_hours),
        longest: displayValue(stat?.max_length_hours),
        shortest: displayCount(stat?.topics_count),
      };
    });
  }, [categoryStats]);

  return (
    <div className="page landing">
      <div className="theme-toggle-floating">
        <ThemeToggle />
      </div>
      <header className="landing-nav">
        <div className="brand">
          <span className="brand-mark">E</span>
          <div>
            <h1>Echoman</h1>
            <p className="tagline">每个回声会持续多久？</p>
          </div>
        </div>
        <div className="nav-actions">
          <div className="data-sources">
            数据源：
            <span>{dataSources.join(" / ")}</span>
          </div>
        </div>
      </header>

      <main className="landing-content">
        <section className="hero">
          <div className="hero-text">
            <h2>
              <span className="hero-headline-leading">{headlineLeading}</span>
              {headlineTrailing && (
                <span className="hero-headline-trailing">{headlineTrailing}</span>
              )}
            </h2>
            {/* <p className="hero-description">
              Echoman 记录国内热点的「声量」和「寿命」，结合多平台抓取与 AI 总结，为你绘制事件的完整时间线。
            </p> */}
            <div className="hero-actions">
              <button className="cta" type="button" onClick={() => navigate("/explore")}>
                一探究竟
              </button>
              <span className="cta-hint">信息爆炸时代，热点翻篇比翻书快，Echoman基于AI能力为你记录热点的「声量」和「寿命」</span>
            </div>
          </div>
          <div className="hero-visual">
            <div className="orb orb-1" />
            <div className="orb orb-2" />
            <div className="hero-card">
              <p className="hero-card-title">回声指标</p>
              <div className="hero-card-grid">
                <div>
                  <span className="stat-label">回声强度</span>
                  <span className="stat-value">传播广度</span>
                  <span className="stat-desc">综合多平台热度归一化指标，数值越高表示传播越广。</span>
                </div>
                <div>
                  <span className="stat-label">回声长度</span>
                  <span className="stat-value">持续时间</span>
                  <span className="stat-desc">追踪首发到最新更新的间隔，揭示事件寿命。</span>
                </div>
              </div>
                <p className="hero-card-footer">8:00-22:00 每2小时采集</p>
            </div>
          </div>
        </section>

        <section className="landing-section">
          <header>
            <h3>各类型事件回声均值</h3>
            <p className="section-subtitle">纵览不同类别的生命周期表现</p>
          </header>
          <div className="category-grid">
            {orderedStats.map((stat) => (
              <article className="category-card" key={stat.key}>
                <div
                  className={[
                    "category-card-icon",
                    stat.tone ?? "category-icon-default",
                  ].join(" ")}
                  aria-hidden="true"
                >
                  {stat.icon ?? "📊"}
                </div>
                <div className="category-card-content">
                  <h4>{stat.label}</h4>
                  <dl>
                    <div>
                      <dt>回声平均时长</dt>
                      <dd>{stat.average}</dd>
                    </div>
                    <div>
                      <dt>最长回声时长</dt>
                      <dd>{stat.longest}</dd>
                    </div>
                    <div>
                      <dt>事件数量</dt>
                      <dd>{stat.shortest}</dd>
                    </div>
                  </dl>
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
