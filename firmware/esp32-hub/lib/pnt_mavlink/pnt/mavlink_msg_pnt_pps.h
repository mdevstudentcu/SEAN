#pragma once
// MESSAGE PNT_PPS PACKING

#include <stdint.h>

#define MAVLINK_MSG_ID_PNT_PPS 61001


typedef struct __mavlink_pnt_pps_t {
 uint64_t time_us; /*<  Hub monotonic time of the edge.*/
 uint32_t gps_week; /*<  GPS week the edge belongs to (from the next NMEA/UBX).*/
 uint32_t gps_tow_ms; /*<  GPS time of week at the edge.*/
} mavlink_pnt_pps_t;

#define MAVLINK_MSG_ID_PNT_PPS_LEN 16
#define MAVLINK_MSG_ID_PNT_PPS_MIN_LEN 16
#define MAVLINK_MSG_ID_61001_LEN 16
#define MAVLINK_MSG_ID_61001_MIN_LEN 16

#define MAVLINK_MSG_ID_PNT_PPS_CRC 100
#define MAVLINK_MSG_ID_61001_CRC 100



#if MAVLINK_COMMAND_24BIT
#define MAVLINK_MESSAGE_INFO_PNT_PPS { \
    61001, \
    "PNT_PPS", \
    3, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_pps_t, time_us) }, \
         { "gps_week", NULL, MAVLINK_TYPE_UINT32_T, 0, 8, offsetof(mavlink_pnt_pps_t, gps_week) }, \
         { "gps_tow_ms", NULL, MAVLINK_TYPE_UINT32_T, 0, 12, offsetof(mavlink_pnt_pps_t, gps_tow_ms) }, \
         } \
}
#else
#define MAVLINK_MESSAGE_INFO_PNT_PPS { \
    "PNT_PPS", \
    3, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_pps_t, time_us) }, \
         { "gps_week", NULL, MAVLINK_TYPE_UINT32_T, 0, 8, offsetof(mavlink_pnt_pps_t, gps_week) }, \
         { "gps_tow_ms", NULL, MAVLINK_TYPE_UINT32_T, 0, 12, offsetof(mavlink_pnt_pps_t, gps_tow_ms) }, \
         } \
}
#endif

/**
 * @brief Pack a pnt_pps message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time of the edge.
 * @param gps_week  GPS week the edge belongs to (from the next NMEA/UBX).
 * @param gps_tow_ms  GPS time of week at the edge.
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_pps_pack(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg,
                               uint64_t time_us, uint32_t gps_week, uint32_t gps_tow_ms)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_PPS_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, gps_week);
    _mav_put_uint32_t(buf, 12, gps_tow_ms);

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_PPS_LEN);
#else
    mavlink_pnt_pps_t packet;
    packet.time_us = time_us;
    packet.gps_week = gps_week;
    packet.gps_tow_ms = gps_tow_ms;

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_PPS_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_PPS;
    return mavlink_finalize_message(msg, system_id, component_id, MAVLINK_MSG_ID_PNT_PPS_MIN_LEN, MAVLINK_MSG_ID_PNT_PPS_LEN, MAVLINK_MSG_ID_PNT_PPS_CRC);
}

/**
 * @brief Pack a pnt_pps message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time of the edge.
 * @param gps_week  GPS week the edge belongs to (from the next NMEA/UBX).
 * @param gps_tow_ms  GPS time of week at the edge.
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_pps_pack_status(uint8_t system_id, uint8_t component_id, mavlink_status_t *_status, mavlink_message_t* msg,
                               uint64_t time_us, uint32_t gps_week, uint32_t gps_tow_ms)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_PPS_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, gps_week);
    _mav_put_uint32_t(buf, 12, gps_tow_ms);

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_PPS_LEN);
#else
    mavlink_pnt_pps_t packet;
    packet.time_us = time_us;
    packet.gps_week = gps_week;
    packet.gps_tow_ms = gps_tow_ms;

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_PPS_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_PPS;
#if MAVLINK_CRC_EXTRA
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_PPS_MIN_LEN, MAVLINK_MSG_ID_PNT_PPS_LEN, MAVLINK_MSG_ID_PNT_PPS_CRC);
#else
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_PPS_MIN_LEN, MAVLINK_MSG_ID_PNT_PPS_LEN);
#endif
}

/**
 * @brief Pack a pnt_pps message on a channel
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param time_us  Hub monotonic time of the edge.
 * @param gps_week  GPS week the edge belongs to (from the next NMEA/UBX).
 * @param gps_tow_ms  GPS time of week at the edge.
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_pps_pack_chan(uint8_t system_id, uint8_t component_id, uint8_t chan,
                               mavlink_message_t* msg,
                                   uint64_t time_us,uint32_t gps_week,uint32_t gps_tow_ms)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_PPS_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, gps_week);
    _mav_put_uint32_t(buf, 12, gps_tow_ms);

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_PPS_LEN);
#else
    mavlink_pnt_pps_t packet;
    packet.time_us = time_us;
    packet.gps_week = gps_week;
    packet.gps_tow_ms = gps_tow_ms;

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_PPS_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_PPS;
    return mavlink_finalize_message_chan(msg, system_id, component_id, chan, MAVLINK_MSG_ID_PNT_PPS_MIN_LEN, MAVLINK_MSG_ID_PNT_PPS_LEN, MAVLINK_MSG_ID_PNT_PPS_CRC);
}

/**
 * @brief Encode a pnt_pps struct
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 * @param pnt_pps C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_pps_encode(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg, const mavlink_pnt_pps_t* pnt_pps)
{
    return mavlink_msg_pnt_pps_pack(system_id, component_id, msg, pnt_pps->time_us, pnt_pps->gps_week, pnt_pps->gps_tow_ms);
}

/**
 * @brief Encode a pnt_pps struct on a channel
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param pnt_pps C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_pps_encode_chan(uint8_t system_id, uint8_t component_id, uint8_t chan, mavlink_message_t* msg, const mavlink_pnt_pps_t* pnt_pps)
{
    return mavlink_msg_pnt_pps_pack_chan(system_id, component_id, chan, msg, pnt_pps->time_us, pnt_pps->gps_week, pnt_pps->gps_tow_ms);
}

/**
 * @brief Encode a pnt_pps struct with provided status structure
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 * @param pnt_pps C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_pps_encode_status(uint8_t system_id, uint8_t component_id, mavlink_status_t* _status, mavlink_message_t* msg, const mavlink_pnt_pps_t* pnt_pps)
{
    return mavlink_msg_pnt_pps_pack_status(system_id, component_id, _status, msg,  pnt_pps->time_us, pnt_pps->gps_week, pnt_pps->gps_tow_ms);
}

/**
 * @brief Send a pnt_pps message
 * @param chan MAVLink channel to send the message
 *
 * @param time_us  Hub monotonic time of the edge.
 * @param gps_week  GPS week the edge belongs to (from the next NMEA/UBX).
 * @param gps_tow_ms  GPS time of week at the edge.
 */
#ifdef MAVLINK_USE_CONVENIENCE_FUNCTIONS

static inline void mavlink_msg_pnt_pps_send(mavlink_channel_t chan, uint64_t time_us, uint32_t gps_week, uint32_t gps_tow_ms)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_PPS_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, gps_week);
    _mav_put_uint32_t(buf, 12, gps_tow_ms);

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_PPS, buf, MAVLINK_MSG_ID_PNT_PPS_MIN_LEN, MAVLINK_MSG_ID_PNT_PPS_LEN, MAVLINK_MSG_ID_PNT_PPS_CRC);
#else
    mavlink_pnt_pps_t packet;
    packet.time_us = time_us;
    packet.gps_week = gps_week;
    packet.gps_tow_ms = gps_tow_ms;

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_PPS, (const char *)&packet, MAVLINK_MSG_ID_PNT_PPS_MIN_LEN, MAVLINK_MSG_ID_PNT_PPS_LEN, MAVLINK_MSG_ID_PNT_PPS_CRC);
#endif
}

/**
 * @brief Send a pnt_pps message
 * @param chan MAVLink channel to send the message
 * @param struct The MAVLink struct to serialize
 */
static inline void mavlink_msg_pnt_pps_send_struct(mavlink_channel_t chan, const mavlink_pnt_pps_t* pnt_pps)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    mavlink_msg_pnt_pps_send(chan, pnt_pps->time_us, pnt_pps->gps_week, pnt_pps->gps_tow_ms);
#else
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_PPS, (const char *)pnt_pps, MAVLINK_MSG_ID_PNT_PPS_MIN_LEN, MAVLINK_MSG_ID_PNT_PPS_LEN, MAVLINK_MSG_ID_PNT_PPS_CRC);
#endif
}

#if MAVLINK_MSG_ID_PNT_PPS_LEN <= MAVLINK_MAX_PAYLOAD_LEN
/*
  This variant of _send() can be used to save stack space by reusing
  memory from the receive buffer.  The caller provides a
  mavlink_message_t which is the size of a full mavlink message. This
  is usually the receive buffer for the channel, and allows a reply to an
  incoming message with minimum stack space usage.
 */
static inline void mavlink_msg_pnt_pps_send_buf(mavlink_message_t *msgbuf, mavlink_channel_t chan,  uint64_t time_us, uint32_t gps_week, uint32_t gps_tow_ms)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char *buf = (char *)msgbuf;
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, gps_week);
    _mav_put_uint32_t(buf, 12, gps_tow_ms);

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_PPS, buf, MAVLINK_MSG_ID_PNT_PPS_MIN_LEN, MAVLINK_MSG_ID_PNT_PPS_LEN, MAVLINK_MSG_ID_PNT_PPS_CRC);
#else
    mavlink_pnt_pps_t *packet = (mavlink_pnt_pps_t *)msgbuf;
    packet->time_us = time_us;
    packet->gps_week = gps_week;
    packet->gps_tow_ms = gps_tow_ms;

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_PPS, (const char *)packet, MAVLINK_MSG_ID_PNT_PPS_MIN_LEN, MAVLINK_MSG_ID_PNT_PPS_LEN, MAVLINK_MSG_ID_PNT_PPS_CRC);
#endif
}
#endif

#endif

// MESSAGE PNT_PPS UNPACKING


/**
 * @brief Get field time_us from pnt_pps message
 *
 * @return  Hub monotonic time of the edge.
 */
static inline uint64_t mavlink_msg_pnt_pps_get_time_us(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint64_t(msg,  0);
}

/**
 * @brief Get field gps_week from pnt_pps message
 *
 * @return  GPS week the edge belongs to (from the next NMEA/UBX).
 */
static inline uint32_t mavlink_msg_pnt_pps_get_gps_week(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint32_t(msg,  8);
}

/**
 * @brief Get field gps_tow_ms from pnt_pps message
 *
 * @return  GPS time of week at the edge.
 */
static inline uint32_t mavlink_msg_pnt_pps_get_gps_tow_ms(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint32_t(msg,  12);
}

/**
 * @brief Decode a pnt_pps message into a struct
 *
 * @param msg The message to decode
 * @param pnt_pps C-struct to decode the message contents into
 */
static inline void mavlink_msg_pnt_pps_decode(const mavlink_message_t* msg, mavlink_pnt_pps_t* pnt_pps)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    pnt_pps->time_us = mavlink_msg_pnt_pps_get_time_us(msg);
    pnt_pps->gps_week = mavlink_msg_pnt_pps_get_gps_week(msg);
    pnt_pps->gps_tow_ms = mavlink_msg_pnt_pps_get_gps_tow_ms(msg);
#else
        uint8_t len = msg->len < MAVLINK_MSG_ID_PNT_PPS_LEN? msg->len : MAVLINK_MSG_ID_PNT_PPS_LEN;
        memset(pnt_pps, 0, MAVLINK_MSG_ID_PNT_PPS_LEN);
    memcpy(pnt_pps, _MAV_PAYLOAD(msg), len);
#endif
}
