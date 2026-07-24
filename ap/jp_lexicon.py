"""Japanese occupation lexicon: ISCO-08 unit code -> Japanese surface forms + ambiguity.

Mirrors the English lexicon.py for Layer C (subtitle dialogue). Japanese has no word
boundaries, so matching is SUBSTRING-based (no tokenizer) — high recall, some false
positives, resolved by the same Stage-2 LLM adjudicator. Terms are >= 2 chars to limit
substring noise; genuinely polysemous ones (先生 sensei, 王 king) are flagged ambiguous.

Codes here are a subset of the English LEXICON's renderable set — the occupations that
plausibly surface in spoken dialogue. Membership == renderable-in-subtitles.
"""
from __future__ import annotations

# isco_code -> (japanese_surface_forms, ambiguous)
JP_LEXICON: dict[str, tuple[tuple[str, ...], bool]] = {
    # Managers
    "1120": (("社長", "会長", "重役", "取締役"), True),        # 会長 also club president
    "1411": (("旅館の主人", "宿の主人", "女将"), False),
    "1412": (("料理長",), True),
    "1420": (("店長", "店主"), True),
    # Professionals
    "2111": (("天文学者", "物理学者"), False),
    "2113": (("化学者",), False),
    "2131": (("生物学者", "研究者"), True),                    # 研究者 generic researcher
    "2144": (("機械技師",), False),
    "2151": (("電気技師",), False),
    "2161": (("建築家",), True),
    "2166": (("イラストレーター", "デザイナー"), True),
    "2211": (("医者", "医師", "町医者", "校医"), True),        # 先生 handled under teacher
    "2212": (("外科医", "内科医", "精神科医", "専門医"), False),
    "2221": (("看護師", "看護婦", "ナース"), False),
    "2250": (("獣医",), False),
    "2261": (("歯医者", "歯科医"), False),
    "2262": (("薬剤師",), False),
    "2310": (("教授", "大学教授", "講師"), True),
    "2330": (("先生", "教師", "教員", "担任"), True),          # 先生 = teacher/doctor/master/author
    "2341": (("小学校の先生", "小学校教師"), False),
    "2342": (("保育士", "幼稚園の先生"), False),
    "2411": (("会計士", "経理"), False),
    "2611": (("弁護士", "検事", "検察官"), True),              # 検事 prosecutor
    "2612": (("裁判官", "判事"), True),
    "2622": (("司書",), False),
    "2634": (("心理学者", "カウンセラー", "セラピスト"), True),
    "2635": (("ソーシャルワーカー",), False),
    "2636": (("僧侶", "神父", "牧師", "尼", "住職", "神主"), True),  # 尼 nun / short
    "2641": (("作家", "小説家", "漫画家", "脚本家"), True),
    "2642": (("記者", "新聞記者", "ジャーナリスト"), True),
    "2643": (("通訳", "翻訳家"), True),
    "2651": (("画家", "芸術家", "彫刻家"), True),
    "2652": (("音楽家", "歌手", "作曲家", "ピアニスト", "ミュージシャン"), True),
    "2653": (("ダンサー", "バレリーナ", "踊り子"), True),
    "2654": (("映画監督", "監督", "プロデューサー"), True),    # 監督 also coach/director
    "2655": (("俳優", "女優", "声優"), True),
    "2656": (("アナウンサー", "司会者"), True),
    "2659": (("アイドル", "芸能人"), True),
    "2512": (("プログラマー", "エンジニア"), True),            # エンジニア broad
    # Technicians / associate professionals
    "3153": (("パイロット", "飛行士"), True),                  # mecha pilot false positive
    "3258": (("救急隊員", "救命士"), False),
    "3311": (("トレーダー", "証券マン"), True),
    "3321": (("保険外交員", "保険屋"), False),
    "3322": (("営業", "セールスマン"), True),                  # 営業 = sales dept/activity
    "3343": (("秘書",), True),
    "3355": (("刑事", "探偵", "捜査官"), True),
    "3421": (("選手", "スポーツ選手", "プロ選手"), True),      # 選手 = player generic
    "3422": (("コーチ", "監督"), True),
    "3431": (("カメラマン", "写真家"), True),
    "3434": (("シェフ", "料理人", "板前"), True),
    # Clerical
    "4110": (("会社員", "サラリーマン", "OL", "事務員"), True),
    "4120": (("秘書",), True),
    "4211": (("銀行員",), False),
    "4222": (("オペレーター",), True),
    "4226": (("受付",), True),                                 # 受付 = reception desk/act
    "4412": (("郵便配達", "郵便屋"), False),
    # Service and sales
    "5111": (("客室乗務員", "スチュワーデス", "CA"), False),
    "5113": (("ガイド", "添乗員"), True),
    "5120": (("コック", "調理師"), True),
    "5131": (("ウェイター", "ウェイトレス", "給仕"), True),
    "5132": (("バーテンダー",), False),
    "5141": (("美容師", "理容師", "床屋"), False),
    "5142": (("エステティシャン",), False),
    "5152": (("執事", "家政婦", "召使い"), True),
    "5221": (("店員", "店主"), True),
    "5223": (("販売員",), False),
    "5230": (("レジ係", "会計係"), True),
    "5241": (("モデル", "ファッションモデル"), True),
    "5246": (("バリスタ", "喫茶店の店員"), True),
    "5311": (("ベビーシッター", "保育士"), False),
    "5321": (("介護士", "介護福祉士"), False),
    "5322": (("ヘルパー", "介護人"), True),
    "5411": (("消防士", "消防隊員"), False),
    "5412": (("警察官", "警官", "巡査", "お巡りさん", "刑事"), True),
    "5413": (("看守", "刑務官"), False),
    "5414": (("警備員", "ボディーガード", "用心棒"), True),
    # Agricultural
    "6111": (("農家", "百姓"), True),
    "6113": (("庭師", "植木屋"), False),
    "6222": (("漁師",), True),
    # Craft / trades
    "7115": (("大工", "宮大工"), False),
    "7126": (("配管工",), False),
    "7212": (("溶接工",), False),
    "7221": (("鍛冶屋", "刀鍛冶"), True),
    "7231": (("整備士", "自動車整備士", "メカニック"), True),
    "7311": (("時計職人",), False),
    "7313": (("宝石職人", "細工師"), True),
    "7314": (("陶芸家",), False),
    "7317": (("職人", "工芸家"), True),                        # 職人 = craftsman (broad)
    "7411": (("電気工", "電気屋"), True),
    "7511": (("肉屋", "魚屋"), True),                          # also shops
    "7512": (("パン職人", "パティシエ", "菓子職人"), False),
    "7531": (("仕立て屋", "お針子"), False),
    "7536": (("靴屋", "靴職人"), True),
    # Plant/machine operators
    "8111": (("鉱夫", "炭鉱夫"), False),
    "8311": (("運転士", "機関士"), True),
    "8322": (("運転手", "タクシー運転手", "運転士"), True),    # 運転手 = driver (broad)
    "8331": (("バス運転手",), False),
    "8332": (("トラック運転手",), False),
    "8350": (("船員", "船乗り", "水兵"), True),                # 水兵 navy sailor
    # Elementary
    "9111": (("メイド", "女中", "お手伝いさん"), True),
    "9112": (("清掃員", "掃除婦", "用務員"), True),
    "9313": (("作業員", "土木作業員", "工事", "現場作業"), True),
    "9412": (("皿洗い",), True),
    "9621": (("配達員", "宅配", "郵便屋", "使い"), True),      # 使い = errand (broad)
    # Armed forces
    "0110": (("将校", "士官", "大佐", "将軍", "司令官"), True),
    "0310": (("兵士", "軍人", "兵隊"), True),
}

# fantasy stratum key (matches lexicon.FANTASY keys) -> (jp forms, ambiguous)
JP_FANTASY: dict[str, tuple[tuple[str, ...], bool]] = {
    "ninja":         (("忍者", "忍び", "くノ一"), False),
    "samurai":       (("侍", "武士", "浪人"), True),
    "mercenary":     (("傭兵",), True),
    "assassin":      (("暗殺者", "殺し屋"), True),
    "bounty_hunter": (("賞金稼ぎ", "賞金首"), True),
    "pirate":        (("海賊",), True),
    "yakuza":        (("ヤクザ", "極道", "組長"), True),
    "knight":        (("騎士", "聖騎士"), False),
    "adventurer":    (("冒険者", "ギルド"), False),
    "mage":          (("魔法使い", "魔導士", "魔女", "魔術師"), False),
    "exorcist":      (("退魔師", "祓魔師", "陰陽師"), False),
    "shrine_maiden": (("巫女",), False),
    "hero":          (("勇者", "ヒーロー"), True),
    "shinigami":     (("死神",), False),
    "royalty":       (("王子", "王女", "姫", "国王", "女王", "皇帝"), True),
    "noble":         (("貴族", "令嬢", "公爵", "伯爵", "男爵"), True),
    "monster_hunter": (("討伐", "退治"), True),
    "summoner":      (("召喚士", "テイマー"), False),
    "alchemist":     (("錬金術師",), False),
}
