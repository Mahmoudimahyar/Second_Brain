"use client";

/**
 * TopicTrendChart — Recharts LineChart for time-window topic
 * volume + sentiment per 07-component-vocabulary.md §6.
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface TrendPoint {
  date: string;
  volume: number;
  sentiment: number;
}

export interface TopicTrendChartProps {
  title?: string;
  data: TrendPoint[];
  height?: number;
}

export function TopicTrendChart({
  title = "Trend",
  data,
  height = 220,
}: TopicTrendChartProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="topicArea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.4} />
                <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="2 4" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              axisLine={false}
              width={32}
            />
            <Tooltip
              cursor={{ stroke: "hsl(var(--primary))", strokeWidth: 1 }}
              contentStyle={{
                background: "hsl(var(--surface-elevated))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "0.5rem",
                fontSize: 11,
              }}
            />
            <Area
              type="monotone"
              dataKey="volume"
              stroke="hsl(var(--primary))"
              fill="url(#topicArea)"
            />
            <Line
              type="monotone"
              dataKey="sentiment"
              stroke="hsl(var(--accent))"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
