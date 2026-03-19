#!/bin/bash
cd /mnt/c/Users/Curry/Desktop/NBA_Logos
rm -f *.svg *.png 2>/dev/null

# NBA球队代码和中文名
declare -A teams=(
    ["ATL"]="老鹰"
    ["BOS"]="凯尔特人"
    ["BKN"]="篮网"
    ["CHA"]="黄蜂"
    ["CHI"]="公牛"
    ["CLE"]="骑士"
    ["DAL"]="独行侠"
    ["DEN"]="掘金"
    ["DET"]="活塞"
    ["GSW"]="勇士"
    ["HOU"]="火箭"
    ["IND"]="步行者"
    ["LAC"]="快船"
    ["LAL"]="湖人"
    ["MEM"]="灰熊"
    ["MIA"]="热火"
    ["MIL"]="雄鹿"
    ["MIN"]="森林狼"
    ["NOP"]="鹈鹕"
    ["NYK"]="尼克斯"
    ["OKC"]="雷霆"
    ["ORL"]="魔术"
    ["PHI"]="76人"
    ["PHX"]="太阳"
    ["POR"]="开拓者"
    ["SAC"]="国王"
    ["SAS"]="马刺"
    ["TOR"]="猛龙"
    ["UTA"]="爵士"
    ["WAS"]="奇才"
)

# 下载logo
for code in "${!teams[@]}"; do
    name="${teams[$code]}"
    # 使用虎扑的logo
    url="https://nba.hupu.com/assets/images/teams/${code}.png"
    curl -sL "$url" -o "${name}.png" &
done

wait
echo "下载完成!"
ls -la *.png 2>/dev/null | wc -l
echo "个PNG文件"
