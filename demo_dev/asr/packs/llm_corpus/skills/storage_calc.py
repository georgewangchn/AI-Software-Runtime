def calculate_storage(facts: dict) -> dict:
    """
    Calculate storage requirements based on corpus scale.
    Uses unified facts: Dict[str, Any] interface as per v4.3.
    """
    
    # Extract values from facts using Chinese field names
    data_volume_tb = float(facts.get("语料总规模TB", 0))
    redundancy_factor = float(facts.get("冗余系数", 1.5))
    
    # Calculate total storage
    total_storage_tb = data_volume_tb * redundancy_factor
    
    # Return structured result
    return {
        "存储总规模TB": total_storage_tb,
        "冗余系数": redundancy_factor,
        "存储类型": "分布式对象存储"
    }