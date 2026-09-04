from ml.rolling import build_player_feature
from ml.team_feature import build_team_feature

blue = [
    build_player_feature("LLLM", "TrayB"),
    build_player_feature("Symphony of Trag", "greed"),
    build_player_feature("Midro", "ttttt"),
    build_player_feature("THSGMDALSDMFAKSE", "DWEHU"),
    build_player_feature("Slayer09", "pro"),
]

red = [
    build_player_feature("ONG Blowz", "206"),
    build_player_feature("ilya", "zzzz"),
    build_player_feature("eminem", "VGOD"),
    build_player_feature("Faither", "2025"),
    build_player_feature("환 희", "1112"),
]

X = build_team_feature(blue, red)

print(X.shape)
print(X.columns)
print(X)