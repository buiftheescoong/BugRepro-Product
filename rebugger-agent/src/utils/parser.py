import json
def clean_actions_for_critic(actions):
    """
    Giữ lại tất cả các key ngoại trừ 'id' và 'type' ở cấp root.
    Xóa 'thread_id' bên trong 'args' nếu có.
    """
    if not actions:
        return []

    def clean_single_item(item):
        if not isinstance(item, dict):
            return item
        excluded_top_level = {'id', 'type'}
        cleaned = {k: v for k, v in item.items() if k not in excluded_top_level}        
        return cleaned

    if isinstance(actions, list):
        return [clean_single_item(a) for a in actions]
    return clean_single_item(actions)
