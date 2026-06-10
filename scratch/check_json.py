import json

with open('public/tiles/articles_nomic_data.json', 'r') as f:
    data = json.load(f)

print("has extras:", 'extras' in data)
if 'extras' in data:
    print("extras keys:", list(data['extras'].keys()))
    print("has cluster_label:", 'cluster_label' in data['extras'])
    print("len cluster_label:", len(data['extras']['cluster_label']))
    
print("has cluster_labels_list:", 'cluster_labels_list' in data)
if 'cluster_labels_list' in data:
    print("len cluster_labels_list:", len(data['cluster_labels_list']))
