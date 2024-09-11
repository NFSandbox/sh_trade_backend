import math

import config.general
from exception import error as exc
from schemes import electric as elec_schema
from schemes.electric import BalanceRecord, SQLRecord


def convert_balance_list_to_usage_list(
        record_list: list[BalanceRecord | SQLRecord],
        usage_convert_config: elec_schema.UsageConvertConfig,
) -> list[BalanceRecord]:
    """
    Convert the balance info to usage info of a record list by doing difference calculation.

    Parameters:

    - ``record_list`` List of records. Could be ``BalanceRecord`` or ``SQLRecord``.
    - ``usage_convert_config`` Configs used when converting record list.

    Check out ``UsageConvertConfig`` for more info.

    Notices:

    - The timestamp of passed ``record_list`` must be ascending.
    - The process will be executed as the same order as the one they are in config model.

    Returns:

    A new list with element type of `BalanceRecord` or `SQLRecord`.
    """
    # ensure config received
    if usage_convert_config is None:
        raise exc.ParamError(
            'usage_convert_config',
            'Must provide a valid convert config to usage convert function')

    # create completely new list
    record_list = convert_to_model_record_list(record_list)

    size = len(record_list)
    # Don't deal with empty list
    if size == 0:
        return []

    # iterate from end to start to update the balance to usage.
    # notice no negative usage allowed here. Which will be forcefully pull up to 0
    for i in range(size - 1, 0, -1):
        record_list[i].light_balance = max(0.0, record_list[i - 1].light_balance - record_list[i].light_balance)
        record_list[i].ac_balance = max(0.0, record_list[i - 1].ac_balance - record_list[i].ac_balance)

    # set the first usage record data to zero.
    # for more info about why doing this, check out docs/usage_calc.md
    record_list[0].ac_balance = 0
    record_list[0].light_balance = 0

    # post process of record list

    if usage_convert_config.spreading:
        record_list = usage_list_point_spreading(record_list=record_list)

    if usage_convert_config.use_smart_merge:
        # here None merge_ratio param is allowed
        # which will cause smart_point_merge() to find out smart ratio automatically.
        record_list = smart_points_merge(record_list=record_list, merge_ratio=usage_convert_config.merge_ratio)

    if usage_convert_config.smoothing:
        record_list = usage_list_smoothing(record_list=record_list)

    if usage_convert_config.per_hour_usage:
        record_list = usage_list_unit_convert_to_per_hour(record_list)

    if usage_convert_config.remove_first_point:
        record_list = record_list[1:]

    return record_list


def usage_list_unit_convert_to_per_hour(
        record_list: list[SQLRecord | BalanceRecord]) -> list[BalanceRecord | SQLRecord]:
    """
    Convert the usage list to make the unit become `Usage/Hour`.

    Parameters:

    - ``record_list`` The usage list.

    Returns:

    - List with unit kWh/Hour. Notice that the **original list is also being modified in place**

    Notice:

    - The unit of the first point could not be converted, and would be set to zero
    - For more info, check out ``docs/usage_calc.md``
    """
    # get size and validate size
    size = len(record_list)
    if size == 0:
        return record_list

    # set the usage of first point to zero
    record_list[0].ac_balance = 0
    record_list[0].light_balance = 0

    # iterate rest of the points
    for idx in range(1, size):
        # get the record we need to process
        curr_record = record_list[idx]
        prev_record = record_list[idx - 1]

        # calculate hour distance
        timestamp_distance = curr_record.timestamp - prev_record.timestamp
        hour_distance = timestamp_distance / 3600

        # calculate the value in hour unit
        ac_hour = curr_record.ac_balance / hour_distance
        light_hour = curr_record.light_balance / hour_distance

        # update value
        curr_record.ac_balance = ac_hour
        curr_record.light_balance = light_hour

    # return proceeded list
    return record_list


def usage_list_point_spreading(
        record_list: list[SQLRecord | BalanceRecord]
) -> list[SQLRecord | BalanceRecord]:
    """
    Implement data point spreading on the receiving usage record list then returns it.

    Parameters:

    - ``record_list`` List of **usage** records. Require ascending timestamp.

    Notice if you passing a ``SQLRecord`` list, then this function may mutating the value inside database if some SQLRecord
    instance are in SQLAlchemy Transaction Context.

    For more info about *Data Point Spreading*, check out ``docs/usage_calc.md`` Data Point Spreading part.
    """
    list_len = len(record_list)
    # only list with more than two elements could perform data spreading
    if list_len < 2:
        return record_list

    # spread point distance
    max_dis: int = config.general.POINT_SPREADING_DIS_LIMIT_MIN * 60
    # point spreading threshold
    spreading_dis: int = max_dis + config.general.POINT_SPREADING_TOLERANCE_MIN * 60

    # using a new temporary list to store the newly added point
    # Here use a new list because we can not mutate the list while iterating it.
    added_record_list: list[BalanceRecord] = []

    for cur_idx in range(1, list_len):
        # calculate timestamp distance
        timestamp_diff: int = int(record_list[cur_idx].timestamp - record_list[cur_idx - 1].timestamp)
        # no need for spreading, continue
        if timestamp_diff <= spreading_dis:
            continue

        # calculate point count and new value
        new_point_count: int = (timestamp_diff - 1) // max_dis
        new_value_light: float = round(record_list[cur_idx].light_balance / (new_point_count + 1), 2)
        new_value_ac: float = round(record_list[cur_idx].ac_balance / (new_point_count + 1), 2)

        # update data of the record2
        record_list[cur_idx].light_balance = new_value_light
        record_list[cur_idx].ac_balance = new_value_ac

        # adding new point to waiting list
        current_timestamp = record_list[cur_idx].timestamp
        for back_idx in range(1, new_point_count + 1):
            # calc new point timestamp by offset
            new_timestamp = current_timestamp - back_idx * max_dis
            # add point
            added_record_list.append(BalanceRecord(
                timestamp=new_timestamp,
                light_balance=new_value_light,
                ac_balance=new_value_ac,
            ))

    # merge two list and sort by timestamp ascending
    record_list.extend(added_record_list)
    record_list.sort(key=lambda x: x.timestamp)

    return record_list


def usage_list_smoothing(record_list: list[SQLRecord | BalanceRecord]) -> list[SQLRecord | BalanceRecord]:
    """
    Smoothing a usage record list.

    - ``record_list`` must be **ascending in timestamp**.

    Notice, this function **will NOT mutate the original list object**.

    Returns:

    - A new list of ``BalanceRecord`` list (when received list len >= 3)
    - Original list object (when received list len <3)
    """
    list_len = len(record_list)
    if list_len < 3:
        return record_list

    ratio_list: list[float] = [0.1, 0.7, 0.2]

    # here we need to use a new record list to store the smoothed point
    # because we can NOT mutate the info while iterating throw it.
    new_record_list: list[SQLRecord | BalanceRecord] = []

    new_record_list.append(BalanceRecord(
        timestamp=record_list[0].timestamp,
        light_balance=record_list[0].light_balance,
        ac_balance=record_list[0].ac_balance,
    ))

    for cur_idx in range(1, list_len - 1):
        # create new record in the new list
        new_record_list.append(BalanceRecord())

        # write info into the new record
        new_record_list[cur_idx].light_balance = (
                record_list[cur_idx - 1].light_balance * ratio_list[0] +
                record_list[cur_idx].light_balance * ratio_list[1] +
                record_list[cur_idx + 1].light_balance * ratio_list[2]
        )

        new_record_list[cur_idx].ac_balance = (
                record_list[cur_idx - 1].ac_balance * ratio_list[0] +
                record_list[cur_idx].ac_balance * ratio_list[1] +
                record_list[cur_idx + 1].ac_balance * ratio_list[2]
        )

        new_record_list[cur_idx].timestamp = record_list[cur_idx].timestamp

    new_record_list.append(BalanceRecord(
        timestamp=record_list[-1].timestamp,
        light_balance=record_list[-1].light_balance,
        ac_balance=record_list[-1].ac_balance,
    ))

    return new_record_list


def smart_points_merge(
        record_list: list[SQLRecord | BalanceRecord],
        merge_ratio: int | None,
) -> list[BalanceRecord | SQLRecord]:
    """
    Implement smart usage point merge on received usage record list.

    Parameters:

    - ``record_list``: The original `record_list`, required ascending timestamp.
    - ``merge_ratio``: How many original points will be merged into a new single point. positive ``int`` value

    Returns:

    - New `BalanceRecord` list (when received list len >= `merge_ratio`)
    - Original list. When `ratio==1`, or `list_len < merge_ratio`

    Notice:

    - When merging point, the **usage data will be accumulated instead of calculating the average**.
      This may cause issue if the input usage list uses `Usage/Hour` as the unit.
      This means the Pre Hour Unit Converting should be performed after Smart Point Merge.
    """
    # use auto calculated default ratio
    if merge_ratio is None:
        # calculate default merge ratio use day as density standard
        time_range = record_list[-1].timestamp - record_list[0].timestamp
        merge_ratio = math.floor(time_range / (24 * 60 * 60))

    # merge ratio should be integer
    # merge ratio should >= 1
    merge_ratio = int(merge_ratio)
    merge_ratio = max(1, merge_ratio)

    # the case we directly return original list.
    # 1. The merge ratio is 1, which means don't need to merge.
    # 2. length of the list less than merge ratio. Means the number of points is too few to perform merge.
    list_len = len(record_list)
    if merge_ratio == 1 or list_len < merge_ratio:
        return record_list

    new_record_list: list[BalanceRecord] = []

    # iterate all usage points, with step == merge_ratio
    for cur_idx in range(0, list_len, merge_ratio):
        max_offset: int = min(merge_ratio, list_len - cur_idx)

        # initialize
        sum_ac: float = 0
        sum_light: float = 0
        loop_count: int = 0

        # accumulate usage of the points that being merged.
        for i in range(0, max_offset):
            sum_ac += record_list[cur_idx + i].ac_balance
            sum_light += record_list[cur_idx + i].light_balance
            loop_count += 1

        # use the timestamp of the latest record point.
        last_timestamp = record_list[cur_idx + max_offset - 1].timestamp

        # use the accumulated usage status and latest timestamp to create a new usage record point.
        new_record_list.append(BalanceRecord(
            timestamp=last_timestamp,
            light_balance=sum_light,
            ac_balance=sum_ac,
        ))

    return new_record_list


def convert_to_model_record_list(record_list: list[BalanceRecord | SQLRecord]) -> list[BalanceRecord]:
    """
    Convert a mixed list[BalanceRecord | SQLRecord to pure list[BalanceRecord]

    Return:

    - A new list with all elements are ``BalanceRecord``

    Notice:

    - Converting to pure Pydantic Model list could promise
      all data is well validate including floating point rounding and other fields.
    """
    new_list: list[BalanceRecord] = []
    for record in record_list:
        new_list.append(BalanceRecord(
            timestamp=record.timestamp,
            light_balance=record.light_balance,
            ac_balance=record.ac_balance,
        ))
    return new_list


def time_range_checker(start: int | float, end: int | float) -> None:
    if end is None:
        return

    if start > end:
        raise exc.ParamError(
            '[time_range_params]',
            'The end time should be greater than or equal to the start time')

    if start < 0:
        raise exc.ParamError(
            '[start_time_param]',
            'The start time should be a valid UNIX timestamp which is greater than zero'
        )
