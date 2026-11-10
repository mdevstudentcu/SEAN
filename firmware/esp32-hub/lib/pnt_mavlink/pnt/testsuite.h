/** @file
 *    @brief MAVLink comm protocol testsuite generated from pnt.xml
 *    @see https://mavlink.io/en/
 */
#pragma once
#ifndef PNT_TESTSUITE_H
#define PNT_TESTSUITE_H

#ifdef __cplusplus
extern "C" {
#endif

#ifndef MAVLINK_TEST_ALL
#define MAVLINK_TEST_ALL

static void mavlink_test_pnt(uint8_t, uint8_t, mavlink_message_t *last_msg);

static void mavlink_test_all(uint8_t system_id, uint8_t component_id, mavlink_message_t *last_msg)
{

    mavlink_test_pnt(system_id, component_id, last_msg);
}
#endif




static void mavlink_test_pnt_hub_status(uint8_t system_id, uint8_t component_id, mavlink_message_t *last_msg)
{
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
    mavlink_status_t *status = mavlink_get_channel_status(MAVLINK_COMM_0);
        if ((status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) && MAVLINK_MSG_ID_PNT_HUB_STATUS >= 256) {
            return;
        }
#endif
    mavlink_message_t msg;
        uint8_t buffer[MAVLINK_MAX_PACKET_LEN];
        uint16_t i;
    mavlink_pnt_hub_status_t packet_in = {
        93372036854775807ULL,963497880,963498088,53
    };
    mavlink_pnt_hub_status_t packet1, packet2;
        memset(&packet1, 0, sizeof(packet1));
        packet1.time_us = packet_in.time_us;
        packet1.pps_count = packet_in.pps_count;
        packet1.imu_overruns = packet_in.imu_overruns;
        packet1.gnss_fix = packet_in.gnss_fix;
        
        
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
        if (status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) {
           // cope with extensions
           memset(MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN + (char *)&packet1, 0, sizeof(packet1)-MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN);
        }
#endif
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_hub_status_encode(system_id, component_id, &msg, &packet1);
    mavlink_msg_pnt_hub_status_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_hub_status_pack(system_id, component_id, &msg , packet1.time_us , packet1.pps_count , packet1.imu_overruns , packet1.gnss_fix );
    mavlink_msg_pnt_hub_status_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_hub_status_pack_chan(system_id, component_id, MAVLINK_COMM_0, &msg , packet1.time_us , packet1.pps_count , packet1.imu_overruns , packet1.gnss_fix );
    mavlink_msg_pnt_hub_status_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
        mavlink_msg_to_send_buffer(buffer, &msg);
        for (i=0; i<mavlink_msg_get_send_buffer_length(&msg); i++) {
            comm_send_ch(MAVLINK_COMM_0, buffer[i]);
        }
    mavlink_msg_pnt_hub_status_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);
        
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_hub_status_send(MAVLINK_COMM_1 , packet1.time_us , packet1.pps_count , packet1.imu_overruns , packet1.gnss_fix );
    mavlink_msg_pnt_hub_status_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

#ifdef MAVLINK_HAVE_GET_MESSAGE_INFO
    MAVLINK_ASSERT(mavlink_get_message_info_by_name("PNT_HUB_STATUS") != NULL);
    MAVLINK_ASSERT(mavlink_get_message_info_by_id(MAVLINK_MSG_ID_PNT_HUB_STATUS) != NULL);
#endif
}

static void mavlink_test_pnt_pps(uint8_t system_id, uint8_t component_id, mavlink_message_t *last_msg)
{
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
    mavlink_status_t *status = mavlink_get_channel_status(MAVLINK_COMM_0);
        if ((status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) && MAVLINK_MSG_ID_PNT_PPS >= 256) {
            return;
        }
#endif
    mavlink_message_t msg;
        uint8_t buffer[MAVLINK_MAX_PACKET_LEN];
        uint16_t i;
    mavlink_pnt_pps_t packet_in = {
        93372036854775807ULL,963497880,963498088
    };
    mavlink_pnt_pps_t packet1, packet2;
        memset(&packet1, 0, sizeof(packet1));
        packet1.time_us = packet_in.time_us;
        packet1.gps_week = packet_in.gps_week;
        packet1.gps_tow_ms = packet_in.gps_tow_ms;
        
        
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
        if (status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) {
           // cope with extensions
           memset(MAVLINK_MSG_ID_PNT_PPS_MIN_LEN + (char *)&packet1, 0, sizeof(packet1)-MAVLINK_MSG_ID_PNT_PPS_MIN_LEN);
        }
#endif
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_pps_encode(system_id, component_id, &msg, &packet1);
    mavlink_msg_pnt_pps_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_pps_pack(system_id, component_id, &msg , packet1.time_us , packet1.gps_week , packet1.gps_tow_ms );
    mavlink_msg_pnt_pps_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_pps_pack_chan(system_id, component_id, MAVLINK_COMM_0, &msg , packet1.time_us , packet1.gps_week , packet1.gps_tow_ms );
    mavlink_msg_pnt_pps_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
        mavlink_msg_to_send_buffer(buffer, &msg);
        for (i=0; i<mavlink_msg_get_send_buffer_length(&msg); i++) {
            comm_send_ch(MAVLINK_COMM_0, buffer[i]);
        }
    mavlink_msg_pnt_pps_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);
        
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_pps_send(MAVLINK_COMM_1 , packet1.time_us , packet1.gps_week , packet1.gps_tow_ms );
    mavlink_msg_pnt_pps_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

#ifdef MAVLINK_HAVE_GET_MESSAGE_INFO
    MAVLINK_ASSERT(mavlink_get_message_info_by_name("PNT_PPS") != NULL);
    MAVLINK_ASSERT(mavlink_get_message_info_by_id(MAVLINK_MSG_ID_PNT_PPS) != NULL);
#endif
}

static void mavlink_test_pnt_imu_raw(uint8_t system_id, uint8_t component_id, mavlink_message_t *last_msg)
{
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
    mavlink_status_t *status = mavlink_get_channel_status(MAVLINK_COMM_0);
        if ((status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) && MAVLINK_MSG_ID_PNT_IMU_RAW >= 256) {
            return;
        }
#endif
    mavlink_message_t msg;
        uint8_t buffer[MAVLINK_MAX_PACKET_LEN];
        uint16_t i;
    mavlink_pnt_imu_raw_t packet_in = {
        93372036854775807ULL,{ 73.0, 74.0, 75.0 },{ 157.0, 158.0, 159.0 },241.0
    };
    mavlink_pnt_imu_raw_t packet1, packet2;
        memset(&packet1, 0, sizeof(packet1));
        packet1.time_us = packet_in.time_us;
        packet1.temp = packet_in.temp;
        
        mav_array_memcpy(packet1.accel, packet_in.accel, sizeof(float)*3);
        mav_array_memcpy(packet1.gyro, packet_in.gyro, sizeof(float)*3);
        
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
        if (status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) {
           // cope with extensions
           memset(MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN + (char *)&packet1, 0, sizeof(packet1)-MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN);
        }
#endif
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_imu_raw_encode(system_id, component_id, &msg, &packet1);
    mavlink_msg_pnt_imu_raw_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_imu_raw_pack(system_id, component_id, &msg , packet1.time_us , packet1.accel , packet1.gyro , packet1.temp );
    mavlink_msg_pnt_imu_raw_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_imu_raw_pack_chan(system_id, component_id, MAVLINK_COMM_0, &msg , packet1.time_us , packet1.accel , packet1.gyro , packet1.temp );
    mavlink_msg_pnt_imu_raw_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
        mavlink_msg_to_send_buffer(buffer, &msg);
        for (i=0; i<mavlink_msg_get_send_buffer_length(&msg); i++) {
            comm_send_ch(MAVLINK_COMM_0, buffer[i]);
        }
    mavlink_msg_pnt_imu_raw_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);
        
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_imu_raw_send(MAVLINK_COMM_1 , packet1.time_us , packet1.accel , packet1.gyro , packet1.temp );
    mavlink_msg_pnt_imu_raw_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

#ifdef MAVLINK_HAVE_GET_MESSAGE_INFO
    MAVLINK_ASSERT(mavlink_get_message_info_by_name("PNT_IMU_RAW") != NULL);
    MAVLINK_ASSERT(mavlink_get_message_info_by_id(MAVLINK_MSG_ID_PNT_IMU_RAW) != NULL);
#endif
}

static void mavlink_test_pnt_baro(uint8_t system_id, uint8_t component_id, mavlink_message_t *last_msg)
{
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
    mavlink_status_t *status = mavlink_get_channel_status(MAVLINK_COMM_0);
        if ((status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) && MAVLINK_MSG_ID_PNT_BARO >= 256) {
            return;
        }
#endif
    mavlink_message_t msg;
        uint8_t buffer[MAVLINK_MAX_PACKET_LEN];
        uint16_t i;
    mavlink_pnt_baro_t packet_in = {
        93372036854775807ULL,73.0,101.0
    };
    mavlink_pnt_baro_t packet1, packet2;
        memset(&packet1, 0, sizeof(packet1));
        packet1.time_us = packet_in.time_us;
        packet1.pressure = packet_in.pressure;
        packet1.temp = packet_in.temp;
        
        
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
        if (status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) {
           // cope with extensions
           memset(MAVLINK_MSG_ID_PNT_BARO_MIN_LEN + (char *)&packet1, 0, sizeof(packet1)-MAVLINK_MSG_ID_PNT_BARO_MIN_LEN);
        }
#endif
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_baro_encode(system_id, component_id, &msg, &packet1);
    mavlink_msg_pnt_baro_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_baro_pack(system_id, component_id, &msg , packet1.time_us , packet1.pressure , packet1.temp );
    mavlink_msg_pnt_baro_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_baro_pack_chan(system_id, component_id, MAVLINK_COMM_0, &msg , packet1.time_us , packet1.pressure , packet1.temp );
    mavlink_msg_pnt_baro_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
        mavlink_msg_to_send_buffer(buffer, &msg);
        for (i=0; i<mavlink_msg_get_send_buffer_length(&msg); i++) {
            comm_send_ch(MAVLINK_COMM_0, buffer[i]);
        }
    mavlink_msg_pnt_baro_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);
        
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_baro_send(MAVLINK_COMM_1 , packet1.time_us , packet1.pressure , packet1.temp );
    mavlink_msg_pnt_baro_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

#ifdef MAVLINK_HAVE_GET_MESSAGE_INFO
    MAVLINK_ASSERT(mavlink_get_message_info_by_name("PNT_BARO") != NULL);
    MAVLINK_ASSERT(mavlink_get_message_info_by_id(MAVLINK_MSG_ID_PNT_BARO) != NULL);
#endif
}

static void mavlink_test_pnt_wifi_ap(uint8_t system_id, uint8_t component_id, mavlink_message_t *last_msg)
{
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
    mavlink_status_t *status = mavlink_get_channel_status(MAVLINK_COMM_0);
        if ((status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) && MAVLINK_MSG_ID_PNT_WIFI_AP >= 256) {
            return;
        }
#endif
    mavlink_message_t msg;
        uint8_t buffer[MAVLINK_MAX_PACKET_LEN];
        uint16_t i;
    mavlink_pnt_wifi_ap_t packet_in = {
        93372036854775807ULL,{ 29, 30, 31, 32, 33, 34, 35, 36 },53,120,187
    };
    mavlink_pnt_wifi_ap_t packet1, packet2;
        memset(&packet1, 0, sizeof(packet1));
        packet1.time_us = packet_in.time_us;
        packet1.rssi = packet_in.rssi;
        packet1.channel = packet_in.channel;
        packet1.ftm_responder = packet_in.ftm_responder;
        
        mav_array_memcpy(packet1.bssid_hash, packet_in.bssid_hash, sizeof(uint8_t)*8);
        
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
        if (status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) {
           // cope with extensions
           memset(MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN + (char *)&packet1, 0, sizeof(packet1)-MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN);
        }
#endif
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_wifi_ap_encode(system_id, component_id, &msg, &packet1);
    mavlink_msg_pnt_wifi_ap_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_wifi_ap_pack(system_id, component_id, &msg , packet1.time_us , packet1.bssid_hash , packet1.rssi , packet1.channel , packet1.ftm_responder );
    mavlink_msg_pnt_wifi_ap_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_wifi_ap_pack_chan(system_id, component_id, MAVLINK_COMM_0, &msg , packet1.time_us , packet1.bssid_hash , packet1.rssi , packet1.channel , packet1.ftm_responder );
    mavlink_msg_pnt_wifi_ap_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
        mavlink_msg_to_send_buffer(buffer, &msg);
        for (i=0; i<mavlink_msg_get_send_buffer_length(&msg); i++) {
            comm_send_ch(MAVLINK_COMM_0, buffer[i]);
        }
    mavlink_msg_pnt_wifi_ap_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);
        
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_wifi_ap_send(MAVLINK_COMM_1 , packet1.time_us , packet1.bssid_hash , packet1.rssi , packet1.channel , packet1.ftm_responder );
    mavlink_msg_pnt_wifi_ap_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

#ifdef MAVLINK_HAVE_GET_MESSAGE_INFO
    MAVLINK_ASSERT(mavlink_get_message_info_by_name("PNT_WIFI_AP") != NULL);
    MAVLINK_ASSERT(mavlink_get_message_info_by_id(MAVLINK_MSG_ID_PNT_WIFI_AP) != NULL);
#endif
}

static void mavlink_test_pnt_ftm_range(uint8_t system_id, uint8_t component_id, mavlink_message_t *last_msg)
{
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
    mavlink_status_t *status = mavlink_get_channel_status(MAVLINK_COMM_0);
        if ((status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) && MAVLINK_MSG_ID_PNT_FTM_RANGE >= 256) {
            return;
        }
#endif
    mavlink_message_t msg;
        uint8_t buffer[MAVLINK_MAX_PACKET_LEN];
        uint16_t i;
    mavlink_pnt_ftm_range_t packet_in = {
        93372036854775807ULL,73.0,101.0,{ 53, 54, 55, 56, 57, 58, 59, 60 },77
    };
    mavlink_pnt_ftm_range_t packet1, packet2;
        memset(&packet1, 0, sizeof(packet1));
        packet1.time_us = packet_in.time_us;
        packet1.range_m = packet_in.range_m;
        packet1.rtt_sigma_ns = packet_in.rtt_sigma_ns;
        packet1.n_frames = packet_in.n_frames;
        
        mav_array_memcpy(packet1.bssid_hash, packet_in.bssid_hash, sizeof(uint8_t)*8);
        
#ifdef MAVLINK_STATUS_FLAG_OUT_MAVLINK1
        if (status->flags & MAVLINK_STATUS_FLAG_OUT_MAVLINK1) {
           // cope with extensions
           memset(MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN + (char *)&packet1, 0, sizeof(packet1)-MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN);
        }
#endif
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_ftm_range_encode(system_id, component_id, &msg, &packet1);
    mavlink_msg_pnt_ftm_range_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_ftm_range_pack(system_id, component_id, &msg , packet1.time_us , packet1.bssid_hash , packet1.range_m , packet1.rtt_sigma_ns , packet1.n_frames );
    mavlink_msg_pnt_ftm_range_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_ftm_range_pack_chan(system_id, component_id, MAVLINK_COMM_0, &msg , packet1.time_us , packet1.bssid_hash , packet1.range_m , packet1.rtt_sigma_ns , packet1.n_frames );
    mavlink_msg_pnt_ftm_range_decode(&msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

        memset(&packet2, 0, sizeof(packet2));
        mavlink_msg_to_send_buffer(buffer, &msg);
        for (i=0; i<mavlink_msg_get_send_buffer_length(&msg); i++) {
            comm_send_ch(MAVLINK_COMM_0, buffer[i]);
        }
    mavlink_msg_pnt_ftm_range_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);
        
        memset(&packet2, 0, sizeof(packet2));
    mavlink_msg_pnt_ftm_range_send(MAVLINK_COMM_1 , packet1.time_us , packet1.bssid_hash , packet1.range_m , packet1.rtt_sigma_ns , packet1.n_frames );
    mavlink_msg_pnt_ftm_range_decode(last_msg, &packet2);
        MAVLINK_ASSERT(memcmp(&packet1, &packet2, sizeof(packet1)) == 0);

#ifdef MAVLINK_HAVE_GET_MESSAGE_INFO
    MAVLINK_ASSERT(mavlink_get_message_info_by_name("PNT_FTM_RANGE") != NULL);
    MAVLINK_ASSERT(mavlink_get_message_info_by_id(MAVLINK_MSG_ID_PNT_FTM_RANGE) != NULL);
#endif
}

static void mavlink_test_pnt(uint8_t system_id, uint8_t component_id, mavlink_message_t *last_msg)
{
    mavlink_test_pnt_hub_status(system_id, component_id, last_msg);
    mavlink_test_pnt_pps(system_id, component_id, last_msg);
    mavlink_test_pnt_imu_raw(system_id, component_id, last_msg);
    mavlink_test_pnt_baro(system_id, component_id, last_msg);
    mavlink_test_pnt_wifi_ap(system_id, component_id, last_msg);
    mavlink_test_pnt_ftm_range(system_id, component_id, last_msg);
}

#ifdef __cplusplus
}
#endif // __cplusplus
#endif // PNT_TESTSUITE_H
