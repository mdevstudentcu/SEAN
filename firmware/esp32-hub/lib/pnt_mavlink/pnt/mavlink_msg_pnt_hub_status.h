#pragma once
// MESSAGE PNT_HUB_STATUS PACKING

#include <stdint.h>

#define MAVLINK_MSG_ID_PNT_HUB_STATUS 61000


typedef struct __mavlink_pnt_hub_status_t {
 uint64_t time_us; /*<  Hub monotonic time.*/
 uint32_t pps_count; /*<  PPS edges seen since boot.*/
 uint32_t imu_overruns; /*<  IMU samples dropped.*/
 uint8_t gnss_fix; /*<  0 none, 2 2D, 3 3D.*/
} mavlink_pnt_hub_status_t;

#define MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN 17
#define MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN 17
#define MAVLINK_MSG_ID_61000_LEN 17
#define MAVLINK_MSG_ID_61000_MIN_LEN 17

#define MAVLINK_MSG_ID_PNT_HUB_STATUS_CRC 57
#define MAVLINK_MSG_ID_61000_CRC 57



#if MAVLINK_COMMAND_24BIT
#define MAVLINK_MESSAGE_INFO_PNT_HUB_STATUS { \
    61000, \
    "PNT_HUB_STATUS", \
    4, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_hub_status_t, time_us) }, \
         { "pps_count", NULL, MAVLINK_TYPE_UINT32_T, 0, 8, offsetof(mavlink_pnt_hub_status_t, pps_count) }, \
         { "imu_overruns", NULL, MAVLINK_TYPE_UINT32_T, 0, 12, offsetof(mavlink_pnt_hub_status_t, imu_overruns) }, \
         { "gnss_fix", NULL, MAVLINK_TYPE_UINT8_T, 0, 16, offsetof(mavlink_pnt_hub_status_t, gnss_fix) }, \
         } \
}
#else
#define MAVLINK_MESSAGE_INFO_PNT_HUB_STATUS { \
    "PNT_HUB_STATUS", \
    4, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_hub_status_t, time_us) }, \
         { "pps_count", NULL, MAVLINK_TYPE_UINT32_T, 0, 8, offsetof(mavlink_pnt_hub_status_t, pps_count) }, \
         { "imu_overruns", NULL, MAVLINK_TYPE_UINT32_T, 0, 12, offsetof(mavlink_pnt_hub_status_t, imu_overruns) }, \
         { "gnss_fix", NULL, MAVLINK_TYPE_UINT8_T, 0, 16, offsetof(mavlink_pnt_hub_status_t, gnss_fix) }, \
         } \
}
#endif

/**
 * @brief Pack a pnt_hub_status message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param pps_count  PPS edges seen since boot.
 * @param imu_overruns  IMU samples dropped.
 * @param gnss_fix  0 none, 2 2D, 3 3D.
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_hub_status_pack(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg,
                               uint64_t time_us, uint32_t pps_count, uint32_t imu_overruns, uint8_t gnss_fix)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, pps_count);
    _mav_put_uint32_t(buf, 12, imu_overruns);
    _mav_put_uint8_t(buf, 16, gnss_fix);

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN);
#else
    mavlink_pnt_hub_status_t packet;
    packet.time_us = time_us;
    packet.pps_count = pps_count;
    packet.imu_overruns = imu_overruns;
    packet.gnss_fix = gnss_fix;

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_HUB_STATUS;
    return mavlink_finalize_message(msg, system_id, component_id, MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_CRC);
}

/**
 * @brief Pack a pnt_hub_status message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param pps_count  PPS edges seen since boot.
 * @param imu_overruns  IMU samples dropped.
 * @param gnss_fix  0 none, 2 2D, 3 3D.
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_hub_status_pack_status(uint8_t system_id, uint8_t component_id, mavlink_status_t *_status, mavlink_message_t* msg,
                               uint64_t time_us, uint32_t pps_count, uint32_t imu_overruns, uint8_t gnss_fix)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, pps_count);
    _mav_put_uint32_t(buf, 12, imu_overruns);
    _mav_put_uint8_t(buf, 16, gnss_fix);

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN);
#else
    mavlink_pnt_hub_status_t packet;
    packet.time_us = time_us;
    packet.pps_count = pps_count;
    packet.imu_overruns = imu_overruns;
    packet.gnss_fix = gnss_fix;

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_HUB_STATUS;
#if MAVLINK_CRC_EXTRA
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_CRC);
#else
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN);
#endif
}

/**
 * @brief Pack a pnt_hub_status message on a channel
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param time_us  Hub monotonic time.
 * @param pps_count  PPS edges seen since boot.
 * @param imu_overruns  IMU samples dropped.
 * @param gnss_fix  0 none, 2 2D, 3 3D.
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_hub_status_pack_chan(uint8_t system_id, uint8_t component_id, uint8_t chan,
                               mavlink_message_t* msg,
                                   uint64_t time_us,uint32_t pps_count,uint32_t imu_overruns,uint8_t gnss_fix)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, pps_count);
    _mav_put_uint32_t(buf, 12, imu_overruns);
    _mav_put_uint8_t(buf, 16, gnss_fix);

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN);
#else
    mavlink_pnt_hub_status_t packet;
    packet.time_us = time_us;
    packet.pps_count = pps_count;
    packet.imu_overruns = imu_overruns;
    packet.gnss_fix = gnss_fix;

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_HUB_STATUS;
    return mavlink_finalize_message_chan(msg, system_id, component_id, chan, MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_CRC);
}

/**
 * @brief Encode a pnt_hub_status struct
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 * @param pnt_hub_status C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_hub_status_encode(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg, const mavlink_pnt_hub_status_t* pnt_hub_status)
{
    return mavlink_msg_pnt_hub_status_pack(system_id, component_id, msg, pnt_hub_status->time_us, pnt_hub_status->pps_count, pnt_hub_status->imu_overruns, pnt_hub_status->gnss_fix);
}

/**
 * @brief Encode a pnt_hub_status struct on a channel
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param pnt_hub_status C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_hub_status_encode_chan(uint8_t system_id, uint8_t component_id, uint8_t chan, mavlink_message_t* msg, const mavlink_pnt_hub_status_t* pnt_hub_status)
{
    return mavlink_msg_pnt_hub_status_pack_chan(system_id, component_id, chan, msg, pnt_hub_status->time_us, pnt_hub_status->pps_count, pnt_hub_status->imu_overruns, pnt_hub_status->gnss_fix);
}

/**
 * @brief Encode a pnt_hub_status struct with provided status structure
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 * @param pnt_hub_status C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_hub_status_encode_status(uint8_t system_id, uint8_t component_id, mavlink_status_t* _status, mavlink_message_t* msg, const mavlink_pnt_hub_status_t* pnt_hub_status)
{
    return mavlink_msg_pnt_hub_status_pack_status(system_id, component_id, _status, msg,  pnt_hub_status->time_us, pnt_hub_status->pps_count, pnt_hub_status->imu_overruns, pnt_hub_status->gnss_fix);
}

/**
 * @brief Send a pnt_hub_status message
 * @param chan MAVLink channel to send the message
 *
 * @param time_us  Hub monotonic time.
 * @param pps_count  PPS edges seen since boot.
 * @param imu_overruns  IMU samples dropped.
 * @param gnss_fix  0 none, 2 2D, 3 3D.
 */
#ifdef MAVLINK_USE_CONVENIENCE_FUNCTIONS

static inline void mavlink_msg_pnt_hub_status_send(mavlink_channel_t chan, uint64_t time_us, uint32_t pps_count, uint32_t imu_overruns, uint8_t gnss_fix)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, pps_count);
    _mav_put_uint32_t(buf, 12, imu_overruns);
    _mav_put_uint8_t(buf, 16, gnss_fix);

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_HUB_STATUS, buf, MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_CRC);
#else
    mavlink_pnt_hub_status_t packet;
    packet.time_us = time_us;
    packet.pps_count = pps_count;
    packet.imu_overruns = imu_overruns;
    packet.gnss_fix = gnss_fix;

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_HUB_STATUS, (const char *)&packet, MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_CRC);
#endif
}

/**
 * @brief Send a pnt_hub_status message
 * @param chan MAVLink channel to send the message
 * @param struct The MAVLink struct to serialize
 */
static inline void mavlink_msg_pnt_hub_status_send_struct(mavlink_channel_t chan, const mavlink_pnt_hub_status_t* pnt_hub_status)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    mavlink_msg_pnt_hub_status_send(chan, pnt_hub_status->time_us, pnt_hub_status->pps_count, pnt_hub_status->imu_overruns, pnt_hub_status->gnss_fix);
#else
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_HUB_STATUS, (const char *)pnt_hub_status, MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_CRC);
#endif
}

#if MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN <= MAVLINK_MAX_PAYLOAD_LEN
/*
  This variant of _send() can be used to save stack space by reusing
  memory from the receive buffer.  The caller provides a
  mavlink_message_t which is the size of a full mavlink message. This
  is usually the receive buffer for the channel, and allows a reply to an
  incoming message with minimum stack space usage.
 */
static inline void mavlink_msg_pnt_hub_status_send_buf(mavlink_message_t *msgbuf, mavlink_channel_t chan,  uint64_t time_us, uint32_t pps_count, uint32_t imu_overruns, uint8_t gnss_fix)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char *buf = (char *)msgbuf;
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_uint32_t(buf, 8, pps_count);
    _mav_put_uint32_t(buf, 12, imu_overruns);
    _mav_put_uint8_t(buf, 16, gnss_fix);

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_HUB_STATUS, buf, MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_CRC);
#else
    mavlink_pnt_hub_status_t *packet = (mavlink_pnt_hub_status_t *)msgbuf;
    packet->time_us = time_us;
    packet->pps_count = pps_count;
    packet->imu_overruns = imu_overruns;
    packet->gnss_fix = gnss_fix;

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_HUB_STATUS, (const char *)packet, MAVLINK_MSG_ID_PNT_HUB_STATUS_MIN_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN, MAVLINK_MSG_ID_PNT_HUB_STATUS_CRC);
#endif
}
#endif

#endif

// MESSAGE PNT_HUB_STATUS UNPACKING


/**
 * @brief Get field time_us from pnt_hub_status message
 *
 * @return  Hub monotonic time.
 */
static inline uint64_t mavlink_msg_pnt_hub_status_get_time_us(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint64_t(msg,  0);
}

/**
 * @brief Get field pps_count from pnt_hub_status message
 *
 * @return  PPS edges seen since boot.
 */
static inline uint32_t mavlink_msg_pnt_hub_status_get_pps_count(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint32_t(msg,  8);
}

/**
 * @brief Get field imu_overruns from pnt_hub_status message
 *
 * @return  IMU samples dropped.
 */
static inline uint32_t mavlink_msg_pnt_hub_status_get_imu_overruns(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint32_t(msg,  12);
}

/**
 * @brief Get field gnss_fix from pnt_hub_status message
 *
 * @return  0 none, 2 2D, 3 3D.
 */
static inline uint8_t mavlink_msg_pnt_hub_status_get_gnss_fix(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint8_t(msg,  16);
}

/**
 * @brief Decode a pnt_hub_status message into a struct
 *
 * @param msg The message to decode
 * @param pnt_hub_status C-struct to decode the message contents into
 */
static inline void mavlink_msg_pnt_hub_status_decode(const mavlink_message_t* msg, mavlink_pnt_hub_status_t* pnt_hub_status)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    pnt_hub_status->time_us = mavlink_msg_pnt_hub_status_get_time_us(msg);
    pnt_hub_status->pps_count = mavlink_msg_pnt_hub_status_get_pps_count(msg);
    pnt_hub_status->imu_overruns = mavlink_msg_pnt_hub_status_get_imu_overruns(msg);
    pnt_hub_status->gnss_fix = mavlink_msg_pnt_hub_status_get_gnss_fix(msg);
#else
        uint8_t len = msg->len < MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN? msg->len : MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN;
        memset(pnt_hub_status, 0, MAVLINK_MSG_ID_PNT_HUB_STATUS_LEN);
    memcpy(pnt_hub_status, _MAV_PAYLOAD(msg), len);
#endif
}
