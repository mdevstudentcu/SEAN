#pragma once
// MESSAGE PNT_WIFI_AP PACKING

#include <stdint.h>

#define MAVLINK_MSG_ID_PNT_WIFI_AP 61004


typedef struct __mavlink_pnt_wifi_ap_t {
 uint64_t time_us; /*<  Hub monotonic time.*/
 uint8_t bssid_hash[8]; /*<  First 8 bytes of SHA-256(salt || BSSID).*/
 int8_t rssi; /*<  dBm*/
 uint8_t channel; /*<  */
 uint8_t ftm_responder; /*<  1 if the AP advertises FTM responder.*/
} mavlink_pnt_wifi_ap_t;

#define MAVLINK_MSG_ID_PNT_WIFI_AP_LEN 19
#define MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN 19
#define MAVLINK_MSG_ID_61004_LEN 19
#define MAVLINK_MSG_ID_61004_MIN_LEN 19

#define MAVLINK_MSG_ID_PNT_WIFI_AP_CRC 173
#define MAVLINK_MSG_ID_61004_CRC 173

#define MAVLINK_MSG_PNT_WIFI_AP_FIELD_BSSID_HASH_LEN 8

#if MAVLINK_COMMAND_24BIT
#define MAVLINK_MESSAGE_INFO_PNT_WIFI_AP { \
    61004, \
    "PNT_WIFI_AP", \
    5, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_wifi_ap_t, time_us) }, \
         { "bssid_hash", NULL, MAVLINK_TYPE_UINT8_T, 8, 8, offsetof(mavlink_pnt_wifi_ap_t, bssid_hash) }, \
         { "rssi", NULL, MAVLINK_TYPE_INT8_T, 0, 16, offsetof(mavlink_pnt_wifi_ap_t, rssi) }, \
         { "channel", NULL, MAVLINK_TYPE_UINT8_T, 0, 17, offsetof(mavlink_pnt_wifi_ap_t, channel) }, \
         { "ftm_responder", NULL, MAVLINK_TYPE_UINT8_T, 0, 18, offsetof(mavlink_pnt_wifi_ap_t, ftm_responder) }, \
         } \
}
#else
#define MAVLINK_MESSAGE_INFO_PNT_WIFI_AP { \
    "PNT_WIFI_AP", \
    5, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_wifi_ap_t, time_us) }, \
         { "bssid_hash", NULL, MAVLINK_TYPE_UINT8_T, 8, 8, offsetof(mavlink_pnt_wifi_ap_t, bssid_hash) }, \
         { "rssi", NULL, MAVLINK_TYPE_INT8_T, 0, 16, offsetof(mavlink_pnt_wifi_ap_t, rssi) }, \
         { "channel", NULL, MAVLINK_TYPE_UINT8_T, 0, 17, offsetof(mavlink_pnt_wifi_ap_t, channel) }, \
         { "ftm_responder", NULL, MAVLINK_TYPE_UINT8_T, 0, 18, offsetof(mavlink_pnt_wifi_ap_t, ftm_responder) }, \
         } \
}
#endif

/**
 * @brief Pack a pnt_wifi_ap message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param bssid_hash  First 8 bytes of SHA-256(salt || BSSID).
 * @param rssi  dBm
 * @param channel  
 * @param ftm_responder  1 if the AP advertises FTM responder.
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_wifi_ap_pack(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg,
                               uint64_t time_us, const uint8_t *bssid_hash, int8_t rssi, uint8_t channel, uint8_t ftm_responder)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_WIFI_AP_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_int8_t(buf, 16, rssi);
    _mav_put_uint8_t(buf, 17, channel);
    _mav_put_uint8_t(buf, 18, ftm_responder);
    _mav_put_uint8_t_array(buf, 8, bssid_hash, 8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN);
#else
    mavlink_pnt_wifi_ap_t packet;
    packet.time_us = time_us;
    packet.rssi = rssi;
    packet.channel = channel;
    packet.ftm_responder = ftm_responder;
    mav_array_memcpy(packet.bssid_hash, bssid_hash, sizeof(uint8_t)*8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_WIFI_AP;
    return mavlink_finalize_message(msg, system_id, component_id, MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_CRC);
}

/**
 * @brief Pack a pnt_wifi_ap message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param bssid_hash  First 8 bytes of SHA-256(salt || BSSID).
 * @param rssi  dBm
 * @param channel  
 * @param ftm_responder  1 if the AP advertises FTM responder.
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_wifi_ap_pack_status(uint8_t system_id, uint8_t component_id, mavlink_status_t *_status, mavlink_message_t* msg,
                               uint64_t time_us, const uint8_t *bssid_hash, int8_t rssi, uint8_t channel, uint8_t ftm_responder)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_WIFI_AP_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_int8_t(buf, 16, rssi);
    _mav_put_uint8_t(buf, 17, channel);
    _mav_put_uint8_t(buf, 18, ftm_responder);
    _mav_put_uint8_t_array(buf, 8, bssid_hash, 8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN);
#else
    mavlink_pnt_wifi_ap_t packet;
    packet.time_us = time_us;
    packet.rssi = rssi;
    packet.channel = channel;
    packet.ftm_responder = ftm_responder;
    mav_array_memcpy(packet.bssid_hash, bssid_hash, sizeof(uint8_t)*8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_WIFI_AP;
#if MAVLINK_CRC_EXTRA
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_CRC);
#else
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN);
#endif
}

/**
 * @brief Pack a pnt_wifi_ap message on a channel
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param time_us  Hub monotonic time.
 * @param bssid_hash  First 8 bytes of SHA-256(salt || BSSID).
 * @param rssi  dBm
 * @param channel  
 * @param ftm_responder  1 if the AP advertises FTM responder.
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_wifi_ap_pack_chan(uint8_t system_id, uint8_t component_id, uint8_t chan,
                               mavlink_message_t* msg,
                                   uint64_t time_us,const uint8_t *bssid_hash,int8_t rssi,uint8_t channel,uint8_t ftm_responder)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_WIFI_AP_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_int8_t(buf, 16, rssi);
    _mav_put_uint8_t(buf, 17, channel);
    _mav_put_uint8_t(buf, 18, ftm_responder);
    _mav_put_uint8_t_array(buf, 8, bssid_hash, 8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN);
#else
    mavlink_pnt_wifi_ap_t packet;
    packet.time_us = time_us;
    packet.rssi = rssi;
    packet.channel = channel;
    packet.ftm_responder = ftm_responder;
    mav_array_memcpy(packet.bssid_hash, bssid_hash, sizeof(uint8_t)*8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_WIFI_AP;
    return mavlink_finalize_message_chan(msg, system_id, component_id, chan, MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_CRC);
}

/**
 * @brief Encode a pnt_wifi_ap struct
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 * @param pnt_wifi_ap C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_wifi_ap_encode(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg, const mavlink_pnt_wifi_ap_t* pnt_wifi_ap)
{
    return mavlink_msg_pnt_wifi_ap_pack(system_id, component_id, msg, pnt_wifi_ap->time_us, pnt_wifi_ap->bssid_hash, pnt_wifi_ap->rssi, pnt_wifi_ap->channel, pnt_wifi_ap->ftm_responder);
}

/**
 * @brief Encode a pnt_wifi_ap struct on a channel
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param pnt_wifi_ap C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_wifi_ap_encode_chan(uint8_t system_id, uint8_t component_id, uint8_t chan, mavlink_message_t* msg, const mavlink_pnt_wifi_ap_t* pnt_wifi_ap)
{
    return mavlink_msg_pnt_wifi_ap_pack_chan(system_id, component_id, chan, msg, pnt_wifi_ap->time_us, pnt_wifi_ap->bssid_hash, pnt_wifi_ap->rssi, pnt_wifi_ap->channel, pnt_wifi_ap->ftm_responder);
}

/**
 * @brief Encode a pnt_wifi_ap struct with provided status structure
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 * @param pnt_wifi_ap C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_wifi_ap_encode_status(uint8_t system_id, uint8_t component_id, mavlink_status_t* _status, mavlink_message_t* msg, const mavlink_pnt_wifi_ap_t* pnt_wifi_ap)
{
    return mavlink_msg_pnt_wifi_ap_pack_status(system_id, component_id, _status, msg,  pnt_wifi_ap->time_us, pnt_wifi_ap->bssid_hash, pnt_wifi_ap->rssi, pnt_wifi_ap->channel, pnt_wifi_ap->ftm_responder);
}

/**
 * @brief Send a pnt_wifi_ap message
 * @param chan MAVLink channel to send the message
 *
 * @param time_us  Hub monotonic time.
 * @param bssid_hash  First 8 bytes of SHA-256(salt || BSSID).
 * @param rssi  dBm
 * @param channel  
 * @param ftm_responder  1 if the AP advertises FTM responder.
 */
#ifdef MAVLINK_USE_CONVENIENCE_FUNCTIONS

static inline void mavlink_msg_pnt_wifi_ap_send(mavlink_channel_t chan, uint64_t time_us, const uint8_t *bssid_hash, int8_t rssi, uint8_t channel, uint8_t ftm_responder)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_WIFI_AP_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_int8_t(buf, 16, rssi);
    _mav_put_uint8_t(buf, 17, channel);
    _mav_put_uint8_t(buf, 18, ftm_responder);
    _mav_put_uint8_t_array(buf, 8, bssid_hash, 8);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_WIFI_AP, buf, MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_CRC);
#else
    mavlink_pnt_wifi_ap_t packet;
    packet.time_us = time_us;
    packet.rssi = rssi;
    packet.channel = channel;
    packet.ftm_responder = ftm_responder;
    mav_array_memcpy(packet.bssid_hash, bssid_hash, sizeof(uint8_t)*8);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_WIFI_AP, (const char *)&packet, MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_CRC);
#endif
}

/**
 * @brief Send a pnt_wifi_ap message
 * @param chan MAVLink channel to send the message
 * @param struct The MAVLink struct to serialize
 */
static inline void mavlink_msg_pnt_wifi_ap_send_struct(mavlink_channel_t chan, const mavlink_pnt_wifi_ap_t* pnt_wifi_ap)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    mavlink_msg_pnt_wifi_ap_send(chan, pnt_wifi_ap->time_us, pnt_wifi_ap->bssid_hash, pnt_wifi_ap->rssi, pnt_wifi_ap->channel, pnt_wifi_ap->ftm_responder);
#else
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_WIFI_AP, (const char *)pnt_wifi_ap, MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_CRC);
#endif
}

#if MAVLINK_MSG_ID_PNT_WIFI_AP_LEN <= MAVLINK_MAX_PAYLOAD_LEN
/*
  This variant of _send() can be used to save stack space by reusing
  memory from the receive buffer.  The caller provides a
  mavlink_message_t which is the size of a full mavlink message. This
  is usually the receive buffer for the channel, and allows a reply to an
  incoming message with minimum stack space usage.
 */
static inline void mavlink_msg_pnt_wifi_ap_send_buf(mavlink_message_t *msgbuf, mavlink_channel_t chan,  uint64_t time_us, const uint8_t *bssid_hash, int8_t rssi, uint8_t channel, uint8_t ftm_responder)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char *buf = (char *)msgbuf;
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_int8_t(buf, 16, rssi);
    _mav_put_uint8_t(buf, 17, channel);
    _mav_put_uint8_t(buf, 18, ftm_responder);
    _mav_put_uint8_t_array(buf, 8, bssid_hash, 8);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_WIFI_AP, buf, MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_CRC);
#else
    mavlink_pnt_wifi_ap_t *packet = (mavlink_pnt_wifi_ap_t *)msgbuf;
    packet->time_us = time_us;
    packet->rssi = rssi;
    packet->channel = channel;
    packet->ftm_responder = ftm_responder;
    mav_array_memcpy(packet->bssid_hash, bssid_hash, sizeof(uint8_t)*8);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_WIFI_AP, (const char *)packet, MAVLINK_MSG_ID_PNT_WIFI_AP_MIN_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN, MAVLINK_MSG_ID_PNT_WIFI_AP_CRC);
#endif
}
#endif

#endif

// MESSAGE PNT_WIFI_AP UNPACKING


/**
 * @brief Get field time_us from pnt_wifi_ap message
 *
 * @return  Hub monotonic time.
 */
static inline uint64_t mavlink_msg_pnt_wifi_ap_get_time_us(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint64_t(msg,  0);
}

/**
 * @brief Get field bssid_hash from pnt_wifi_ap message
 *
 * @return  First 8 bytes of SHA-256(salt || BSSID).
 */
static inline uint16_t mavlink_msg_pnt_wifi_ap_get_bssid_hash(const mavlink_message_t* msg, uint8_t *bssid_hash)
{
    return _MAV_RETURN_uint8_t_array(msg, bssid_hash, 8,  8);
}

/**
 * @brief Get field rssi from pnt_wifi_ap message
 *
 * @return  dBm
 */
static inline int8_t mavlink_msg_pnt_wifi_ap_get_rssi(const mavlink_message_t* msg)
{
    return _MAV_RETURN_int8_t(msg,  16);
}

/**
 * @brief Get field channel from pnt_wifi_ap message
 *
 * @return  
 */
static inline uint8_t mavlink_msg_pnt_wifi_ap_get_channel(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint8_t(msg,  17);
}

/**
 * @brief Get field ftm_responder from pnt_wifi_ap message
 *
 * @return  1 if the AP advertises FTM responder.
 */
static inline uint8_t mavlink_msg_pnt_wifi_ap_get_ftm_responder(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint8_t(msg,  18);
}

/**
 * @brief Decode a pnt_wifi_ap message into a struct
 *
 * @param msg The message to decode
 * @param pnt_wifi_ap C-struct to decode the message contents into
 */
static inline void mavlink_msg_pnt_wifi_ap_decode(const mavlink_message_t* msg, mavlink_pnt_wifi_ap_t* pnt_wifi_ap)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    pnt_wifi_ap->time_us = mavlink_msg_pnt_wifi_ap_get_time_us(msg);
    mavlink_msg_pnt_wifi_ap_get_bssid_hash(msg, pnt_wifi_ap->bssid_hash);
    pnt_wifi_ap->rssi = mavlink_msg_pnt_wifi_ap_get_rssi(msg);
    pnt_wifi_ap->channel = mavlink_msg_pnt_wifi_ap_get_channel(msg);
    pnt_wifi_ap->ftm_responder = mavlink_msg_pnt_wifi_ap_get_ftm_responder(msg);
#else
        uint8_t len = msg->len < MAVLINK_MSG_ID_PNT_WIFI_AP_LEN? msg->len : MAVLINK_MSG_ID_PNT_WIFI_AP_LEN;
        memset(pnt_wifi_ap, 0, MAVLINK_MSG_ID_PNT_WIFI_AP_LEN);
    memcpy(pnt_wifi_ap, _MAV_PAYLOAD(msg), len);
#endif
}
