import utils
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from parallel import apply_parallel, QueuedMap

# PLEASE USE THE GIVEN FUNCTION NAME, DO NOT CHANGE IT

def read_csv(filepath):

    '''
    TODO: This function needs to be completed.
    Read the events.csv, mortality_events.csv and event_feature_map.csv files into events, mortality and feature_map.

    Return events, mortality and feature_map
    '''

    return utils.read_csv(filepath)


def calculate_index_date(events, mortality, deliverables_path):

    '''
    TODO: This function needs to be completed.

    Refer to instructions in Q3 a

    Suggested steps:
    1. Create list of patients alive ( mortality_events.csv only contains information about patients deceased)
    2. Split events into two groups based on whether the patient is alive or deceased
    3. Calculate index date for each patient

    IMPORTANT:
    Save indx_date to a csv file in the deliverables folder named as etl_index_dates.csv.
    Use the global variable deliverables_path while specifying the filepath.
    Each row is of the form patient_id, indx_date.
    The csv file should have a header
    For example if you are using Pandas, you could write:
        indx_date.to_csv(deliverables_path + 'etl_index_dates.csv', columns=['patient_id', 'indx_date'], index=False)

    Return indx_date
    '''
    dead_events, alive_events = utils.split_dead_and_alive(events, mortality)

    def dead_index_finder(df):
        return mortality[mortality.patient_id == df.iloc[0, :].patient_id].iloc[0, :].timestamp - pd.Timedelta(days=30)

    def live_index_finder(df):
        return df.iloc[-1, :].timestamp

    dead_indexes = pd.DataFrame(dead_events.groupby('patient_id').apply(dead_index_finder))

    alive_indexes = pd.DataFrame(alive_events.groupby('patient_id').apply(live_index_finder))

    indx_date = alive_indexes.append(dead_indexes).sort_index()
    indx_date = indx_date.reset_index()
    indx_date.columns = ['patient_id', 'indx_date']

    indx_date.to_csv(deliverables_path + 'etl_index_dates.csv', index=False)

    return indx_date


def filter_events(events, indx_date, deliverables_path):

    '''
    TODO: This function needs to be completed.

    Refer to instructions in Q3 b

    Suggested steps:
    1. Join indx_date with events on patient_id
    2. Filter events occuring in the observation window(IndexDate-2000 to IndexDate)


    IMPORTANT:
    Save filtered_events to a csv file in the deliverables folder named as etl_filtered_events.csv.
    Use the global variable deliverables_path while specifying the filepath.
    Each row is of the form patient_id, event_id, value.
    The csv file should have a header
    For example if you are using Pandas, you could write:
        filtered_events.to_csv(deliverables_path + 'etl_filtered_events.csv', columns=['patient_id', 'event_id', 'value'], index=False)

    Return filtered_events
    '''

    indx_date = indx_date.set_index('patient_id')
    events_w_idx = events.join(indx_date, on='patient_id', how='outer')

    mask_diff = (events_w_idx.indx_date - events_w_idx.timestamp)
    mask = np.logical_and(mask_diff >= pd.Timedelta(days=0),
                          mask_diff <= pd.Timedelta(days=2000))

    filtered_events = events_w_idx[mask]
    filtered_events = filtered_events[['patient_id', 'event_id', 'value']]

    filtered_events.to_csv(deliverables_path + 'etl_filtered_events.csv',
                           columns=['patient_id', 'event_id', 'value'],
                           index=False)


    return filtered_events


def aggregate_events(filtered_events_df, mortality_df,feature_map_df, deliverables_path):

    '''
    TODO: This function needs to be completed.

    Refer to instructions in Q3 c

    Suggested steps:
    1. Replace event_id's with index available in event_feature_map.csv
    2. Remove events with n/a values
    3. Aggregate events using sum and count to calculate feature value
    4. Normalize the values obtained above using min-max normalization(the min value will be 0 in all scenarios)


    IMPORTANT:
    Save aggregated_events to a csv file in the deliverables folder named as etl_aggregated_events.csv.
    Use the global variable deliverables_path while specifying the filepath.
    Each row is of the form patient_id, event_id, value.
    The csv file should have a header .
    For example if you are using Pandas, you could write:
        aggregated_events.to_csv(deliverables_path + 'etl_aggregated_events.csv', columns=['patient_id', 'feature_id', 'feature_value'], index=False)

    Return filtered_events
    '''
    test = feature_map_df

    # 1. Replace event_id's with index available in event_feature_map.csv
    print('Re-mapping feature ids...')
    feature_map_df = feature_map_df.set_index('event_id').to_dict()['idx']

    print filtered_events_df.join(test.set_index('event_id'),
                               on='event_id')

    def remap(x):
        return feature_map_df[x]

    feature_ids = QueuedMap(remap,
                            filtered_events_df.event_id.tolist()).run()

    # feature_ids = filtered_events_df['event_id'].replace(feature_map_df)
    filtered_events_df['feature_id'] = pd.Series(feature_ids,
                                                 index=filtered_events_df.index)

    # 2. Remove events with n/a values
    filtered_events_df = filtered_events_df.dropna()


    # 3. Aggregate events using sum and count to calculate feature value
    def agg_events(df):
        event_name = df.event_id.iloc[0]

        if 'LAB' in event_name:
            return df.patient_id.count()

        elif 'DIAG' in event_name or 'DRUG' in event_name:
            return df.value.sum()

    agg_cols = ['patient_id', 'event_id', 'feature_id']
    aggregated_events = filtered_events_df.groupby(agg_cols)

    print('Calling apply_parallel...')
    aggregated_events = apply_parallel(agg_events, aggregated_events)

    aggregated_events.name = 'feature_value'
    aggregated_events.index = aggregated_events.index.rename(agg_cols)

    aggregated_events = aggregated_events.reset_index()

    # print aggregated_events
    aggregated_events = aggregated_events[['patient_id', 'feature_id',
                                           'feature_value']]


    # 4. Normalize the values obtained above using min-max normalization(the min value will be 0 in all scenarios)
    pivoted = aggregated_events.pivot(index='patient_id',
                                      columns='feature_id',
                                      values='feature_value')

    normed = pivoted/pivoted.max()

    normed = normed.reset_index()
    aggregated_events = pd.melt(normed, id_vars='patient_id',
                                value_name='feature_value').dropna()

    aggregated_events.to_csv(deliverables_path + 'etl_aggregated_events.csv', columns=['patient_id', 'feature_id', 'feature_value'], index=False)

    return aggregated_events

def create_features(events, mortality, feature_map):

    deliverables_path = '../deliverables/'

    #Calculate index date
    print('Calculating index date...')
    indx_date = calculate_index_date(events, mortality, deliverables_path)

    #Filter events in the observation window
    print('Filtering events...')
    filtered_events = filter_events(events, indx_date,  deliverables_path)

    #Aggregate the event values for each patient
    print('Aggregating events...')
    aggregated_events = aggregate_events(filtered_events, mortality, feature_map, deliverables_path)

    '''
    TODO: Complete the code below by creating two dictionaries -
    1. patient_features :  Key - patient_id and value is array of tuples(feature_id, feature_value)
    2. mortality : Key - patient_id and value is mortality label
    '''

    print('Building feature tuples...')
    tuple_dict = aggregated_events.groupby('patient_id').apply(lambda x:
                                                               list(x.sort_values('feature_id').apply(lambda y:
                                                                    (y.feature_id,
                                                                     y.feature_value),
                                                                     axis=1)))
    all_ids = aggregated_events.patient_id.unique()
    is_dead = pd.Series(all_ids, index=all_ids).apply(lambda x: int(x in
                                                           mortality.patient_id))


    patient_features = tuple_dict.to_dict()
    # mortality = is_dead.to_dict()


    dead_ids = list(mortality.patient_id)
    train_labels = [(id, int(id in dead_ids)) for id in list(all_ids)]
    mortality = dict(train_labels)

    return patient_features, mortality

def save_svmlight(patient_features, mortality, op_file, op_deliverable):

    '''
    TODO: This function needs to be completed

    Refer to instructions in Q3 d

    Create two files:
    1. op_file - which saves the features in svmlight format. (See instructions in Q3d for detailed explanation)
    2. op_deliverable - which saves the features in following format:
       patient_id1 label feature_id:feature_value feature_id:feature_value feature_id:feature_value ...
       patient_id2 label feature_id:feature_value feature_id:feature_value feature_id:feature_value ...

    Note: Please make sure the features are ordered in ascending order, and patients are stored in ascending order as well.
    '''
    # op_file = op_deliverable = './'
    deliverable1 = open(op_file, 'wb')
    deliverable2 = open(op_deliverable, 'wb')

    for patient, features in patient_features.iteritems():
        features = pd.DataFrame(features).sort_values(0)

        features = features.values.tolist()

        deliverable1.write("{} {} \n".format(mortality.get(patient, 0),
                                          utils.bag_to_svmlight(features)))
        deliverable2.write("{} {} {} \n".format(int(patient),
                                                mortality.get(patient, 0),
                                             utils.bag_to_svmlight(features)))

def main():
    train_path = '../data/train/'
    events, mortality, feature_map = read_csv(train_path)
    patient_features, mortality = create_features(events.iloc[:, :],
                                                  mortality.iloc[:, :], feature_map)

    print('Saving in svm format...')
    save_svmlight(patient_features, mortality, '../deliverables/features_svmlight.train', '../deliverables/features.train')

if __name__ == "__main__":
    main()
