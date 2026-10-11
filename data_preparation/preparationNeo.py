from collections import Counter
import instructor
import pandas as pd
from pathlib import Path
from openai import OpenAI


def readAndSample(tables, category_col3="Vfc level2 3 Name"):
    if not tables:
        return {}

    dfs_to_concat = []

    # 1. Собираем нужную колонку из всех таблиц
    for name, df in tables.items():
        if category_col3 in df.columns:
            dfs_to_concat.append(df[[category_col3]])

    if not dfs_to_concat:
        return {}

    all_data = pd.concat(dfs_to_concat, ignore_index=True)

    # 2. Фильтруем пустые и невалидные значения
    valid_mask = (
            all_data[category_col3].notna() &
            ~all_data[category_col3].astype(str).str.contains('no_class_found', case=False, na=False) &
            ~all_data[category_col3].astype(str).str.contains('nonclass', case=False, na=False)
    )

    filtered_data = all_data.loc[valid_mask, category_col3].astype(str)
    total_valid = len(filtered_data)

    if total_valid == 0:
        return {}

    # 3. Разбиваем колонку на две части по ПЕРВОМУ двоеточию
    # expand=True создает DataFrame из двух колонок:
    # 0 - Ключ (до двоеточия), 1 - Комментарий (после двоеточия)
    split_data = filtered_data.str.split(':', n=1, expand=True)

    # Очищаем ключи от пробелов
    split_data[0] = split_data[0].str.strip()

    # Если в данных не было ни одного двоеточия, второй колонки не будет, поэтому проверяем
    if 1 in split_data.columns:
        # Очищаем вторую часть (комментарий) от пробелов, а пустые значения заменяем на пустую строку
        split_data[1] = split_data[1].str.strip().fillna("")
    else:
        split_data[1] = ""

    # 4. Группируем данные по ключу (колонке 0)
    result_hashmap = {}
    grouped = split_data.groupby(0)

    for key, group_df in grouped:
        # Считаем процент (количество строк в группе / общее количество * 100)
        percentage = round((len(group_df) / total_valid) * 100, 2)

        # Собираем все комментарии (колонка 1) в список, исключая пустые строки
        comments_list = [comment for comment in group_df[1].tolist() if comment]

        # Записываем в хешмапу кортеж: (процент, список_комментариев)
        result_hashmap[key] = (percentage, comments_list)

    return result_hashmap


def calculateCommentProbabilities(result_hashmap):
    """Возвращает долю каждого комментария внутри его ключа в процентах."""
    return {
        key: (
            percentage,
            {
                comment: round(count / len(comments) * 100, 2)
                for comment, count in Counter(comments).items()
            },
        )
        for key, (percentage, comments) in result_hashmap.items()
    }

