from predictor import predict_blue_win

blue = [
    {"name":"LLLM","tag":"TrayB"},
    {"name":"Symphony of Trag","tag":"greed"},
    {"name":"Midro","tag":"ttttt"},
    {"name":"THSGMDALSDMFAKSE","tag":"DWEHU"},
    {"name":"Slayer09","tag":"pro"},
]

red = [
    {"name":"ONG Blowz","tag":"206"},
    {"name":"ilya","tag":"zzzz"},
    {"name":"eminem","tag":"VGOD"},
    {"name":"Faither","tag":"2025"},
    {"name":"환 희","tag":"1112"},
]

result = predict_blue_win(
    blue,
    red,
    save_json=True
)

print(result)