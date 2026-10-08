import pandas as pd


pok = pd.read_csv("pokazaniya.csv", sep=";")
sob = pd.read_csv("sobytiya.csv", sep=";")

pok["data"] = pd.to_datetime(pok["data"])
sob["data"] = pd.to_datetime(sob["data"])

pok = pok.sort_values(["anon_id", "data"])


pok["days"] = pok.groupby("anon_id")["data"].diff().dt.days
pok["rashod"] = pok.groupby("anon_id")["pokazanie"].diff()

pok.loc[pok["days"] != 1, "rashod"] = pd.NA

pok["median"] = pok.groupby("anon_id")["rashod"].transform("median")


negative = pok[pok["rashod"] < 0]

print("\n1. ОТРИЦАТЕЛЬНЫЙ РАСХОД")
print("Критерий: расход < 0")
print("Приборов:", negative["anon_id"].nunique())
print(negative[["anon_id", "data", "rashod"]]
      .sort_values("rashod").head(10))



spikes = pok[
    (pok["rashod"] > 100) &
    (pok["rashod"] > pok["median"] * 3)
]

print("\n2. ВСПЛЕСКИ")
print("Критерий: >100 м³/сутки и >3× обычного расхода")
print("Приборов:", spikes["anon_id"].nunique())
print(spikes[["anon_id", "data", "rashod", "median"]]
      .sort_values("rashod", ascending=False).head(10))



impossible = pok[pok["rashod"] > 1000]

print("\n3. НЕРЕАЛИСТИЧНЫЕ ЗНАЧЕНИЯ")
print("Критерий: >1000 м³/сутки")
print("Приборов:", impossible["anon_id"].nunique())
print(impossible[["anon_id", "data", "rashod"]]
      .sort_values("rashod", ascending=False).head(10))



def find_sequences(df, condition, days):
    result = set()

    for meter, g in df.groupby("anon_id"):
        g = g.sort_values("data").reset_index(drop=True)

        for i in range(days - 1, len(g)):
            part = g.iloc[i - days + 1:i + 1]

            consecutive = (
                part["data"].diff().dt.days.iloc[1:] == 1
            ).all()

            if consecutive and condition(part).all():
                result.add(meter)
                break

    return result


leak_ids = find_sequences(
    pok,
    lambda x: x["rashod"] > 0.01,
    14
)

print("\n4. ВОЗМОЖНАЯ УТЕЧКА")
print("Критерий: расход >0.01 м³/сутки 14 дней подряд")
print("Приборов:", len(leak_ids))
print("Примеры:", list(leak_ids)[:10])



zero_ids = find_sequences(
    pok,
    lambda x: (
        (x["rashod"] == 0) &
        (x["paketov_za_sutki"] > 0)
    ),
    7
)

print("\n5. НУЛЕВОЙ РАСХОД + ПАКЕТЫ")
print("Критерий: 0 м³ 7 дней подряд, но пакеты идут")
print("Приборов:", len(zero_ids))
print("Примеры:", list(zero_ids)[:10])



mid = pok["data"].min() + (
    pok["data"].max() - pok["data"].min()
) / 2

first = (
    pok[pok["data"] <= mid]
    .groupby("anon_id")["rashod"]
    .agg(["median", "count"])
)

second = (
    pok[pok["data"] > mid]
    .groupby("anon_id")["rashod"]
    .agg(["median", "count"])
)

step = first.join(
    second,
    lsuffix="_first",
    rsuffix="_second"
).dropna()


step = step[
    (step["count_first"] >= 14) &
    (step["count_second"] >= 14)
]


step = step[
    step["median_first"] > 0.01
]

step = step[
    step["median_second"] > 0.01
]

step["ratio"] = (
    step["median_second"] /
    step["median_first"]
)


step = step[
    (step["ratio"] >= 2) |
    (step["ratio"] <= 0.5)
]

print("\n6. СТУПЕНЬКА")
print(
    "Критерий: устойчивое изменение расхода "
    "минимум в 2 раза, без перехода в ноль"
)
print("Приборов:", len(step))

print(
    step[
        ["median_first", "median_second", "ratio"]
    ]
    .sort_values("ratio")
    .head(10)
)



magnet = sob[
    sob["sobytie"]
    .astype(str)
    .str.lower()
    .str.contains("магнит", na=False)
].drop_duplicates(["anon_id", "data"])

before = pok[["anon_id", "data", "rashod"]].copy()
before["data"] += pd.Timedelta(days=1)
before = before.rename(columns={"rashod": "before"})

after = pok[["anon_id", "data", "rashod"]].copy()
after["data"] -= pd.Timedelta(days=1)
after = after.rename(columns={"rashod": "after"})

m = (
    magnet
    .merge(before, on=["anon_id", "data"], how="left")
    .merge(after, on=["anon_id", "data"], how="left")
)

m = m[
    (m["before"] > 0) &
    (m["after"] >= 0)
]

m["drop"] = 1 - m["after"] / m["before"]

magnet_drop = m[m["drop"] >= 0.5]

print("\n7. СВЯЗЬ С 'МАГНИТОМ'")
print("Всего событий:", len(magnet))
print("С данными до/после:", len(m))
print("Падение расхода >=50%:", len(magnet_drop))




pok["next"] = pok.groupby("anon_id")["rashod"].shift(-1)

reversal = pok[
    (pok["rashod"] > 100) &
    (pok["next"] < 0)
]

print("\n8. СОБСТВЕННАЯ НАХОДКА")
print("Большой скачок → отрицательный расход")
print("Приборов:", reversal["anon_id"].nunique())

print(
    reversal[
        ["anon_id", "data", "rashod", "next"]
    ]
    .sort_values("rashod", ascending=False)
    .head(10)
)




priority = {}

def add(ids, reason):
    for x in ids:
        priority.setdefault(x, []).append(reason)

add(negative["anon_id"].unique(), "отрицательный расход")
add(spikes["anon_id"].unique(), "всплеск")
add(impossible["anon_id"].unique(), "нереальный расход")
add(leak_ids, "возможная утечка")
add(zero_ids, "ноль + пакеты")
add(step.index, "ступенька")
add(magnet_drop["anon_id"].unique(), "падение после магнита")

result = pd.DataFrame([
    [x, len(r), ", ".join(r)]
    for x, r in priority.items()
], columns=["anon_id", "аномалий", "причины"])

print("\n" + "=" * 60)
print("ПРИБОРЫ ДЛЯ ПЕРВОЙ ПРОВЕРКИ")
print("=" * 60)

print(
    result
    .sort_values("аномалий", ascending=False)
    .head(20)
    .to_string(index=False)
)