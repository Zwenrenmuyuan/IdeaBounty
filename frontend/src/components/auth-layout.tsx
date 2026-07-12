import type { ReactNode } from "react";
import { Coins, ShieldCheck, Sparkles } from "lucide-react";
import { BrandMark } from "@/components/brand-mark";

const FEATURES = [
  { icon: Sparkles, text: "AI 结构化评估商业价值" },
  { icon: ShieldCheck, text: "跨投稿查重并保护隐私" },
  { icon: Coins, text: "透明规则估算点子红包" },
];

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="grid min-h-screen lg:grid-cols-[1.05fr_0.95fr]">
      <section
        className={
          "relative hidden overflow-hidden bg-primary px-12 py-14 text-primary-foreground " +
          "lg:flex lg:flex-col lg:justify-between"
        }
      >
        <div className="absolute -right-24 -top-24 size-80 rounded-full bg-amber-300/15 blur-3xl" />
        <div
          className="absolute -bottom-32 -left-16 size-96 rounded-full bg-blue-300/10 blur-3xl"
        />
        <div className="relative flex items-center gap-3">
          <BrandMark className="size-11" />
          <span className="text-xl font-semibold tracking-tight">Idea Bounty</span>
        </div>
        <div className="relative max-w-lg">
          <p className="mb-4 text-sm font-medium tracking-[0.2em] text-amber-200">
            让好点子被认真看见
          </p>
          <h1 className="text-4xl font-semibold leading-tight tracking-tight xl:text-5xl">
            记录真实痛点，
            <br />
            让 AI 帮你发现价值。
          </h1>
          <div className="mt-10 space-y-4">
            {FEATURES.map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-center gap-3 text-primary-foreground/75">
                <span className="flex size-8 items-center justify-center rounded-lg bg-white/10">
                  <Icon className="size-4 text-amber-200" />
                </span>
                <span className="text-sm">{text}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-primary-foreground/45">
          面试 MVP · 所有支付均为模拟流程
        </p>
      </section>

      <section className="flex min-h-screen items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <BrandMark />
            <span className="text-lg font-semibold tracking-tight">Idea Bounty</span>
          </div>
          {children}
        </div>
      </section>
    </main>
  );
}
