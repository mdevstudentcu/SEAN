#pragma once
// MESSAGE PNT_FTM_RANGE PACKING

#include <stdint.h>

#define MAVLINK_MSG_ID_PNT_FTM_RANGE 61005


typedef struct __mavlink_pnt_ftm_range_t {
 uint64_t time_us; /*<  Hub monotonic time.*/
 float range_m; /*<  */
 float rtt_sigma_ns; /*<  */
 uint8_t bssid_hash[8]; /*<  */
 uint8_t n_frames; /*<  */
} mavlink_pnt_ftm_range_t;

#define MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN 25
#define MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN 25
#define MAVLINK_MSG_ID_61005_LEN 25
#define MAVLINK_MSG_ID_61005_MIN_LEN 25

#define MAVLINK_MSG_ID_PNT_FTM_RANGE_CRC 186
#define MAVLINK_MSG_ID_61005_CRC 186

#define MAVLINK_MSG_PNT_FTM_RANGE_FIELD_BSSID_HASH_LEN 8

#if MAVLINK_COMMAND_24BIT
#define MAVLINK_MESSAGE_INFO_PNT_FTM_RANGE { \
    61005, \
    "PNT_FTM_RANGE", \
    5, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_ftm_range_t, time_us) }, \
         { "bssid_hash", NULL, MAVLINK_TYPE_UINT8_T, 8, 16, offsetof(mavlink_pnt_ftm_range_t, bssid_hash) }, \
         { "range_m", NULL, MAVLINK_TYPE_FLOAT, 0, 8, offsetof(mavlink_pnt_ftm_range_t, range_m) }, \
         { "rtt_sigma_ns", NULL, MAVLINK_TYPE_FLOAT, 0, 12, offsetof(mavlink_pnt_ftm_range_t, rtt_sigma_ns) }, \
         { "n_frames", NULL, MAVLINK_TYPE_UINT8_T, 0, 24, offsetof(mavlink_pnt_ftm_range_t, n_frames) }, \
         } \
}
#else
#define MAVLINK_MESSAGE_INFO_PNT_FTM_RANGE { \
    "PNT_FTM_RANGE", \
    5, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_ftm_range_t, time_us) }, \
         { "bssid_hash", NULL, MAVLINK_TYPE_UINT8_T, 8, 16, offsetof(mavlink_pnt_ftm_range_t, bssid_hash) }, \
         { "range_m", NULL, MAVLINK_TYPE_FLOAT, 0, 8, offsetof(mavlink_pnt_ftm_range_t, range_m) }, \
         { "rtt_sigma_ns", NULL, MAVLINK_TYPE_FLOAT, 0, 12, offsetof(mavlink_pnt_ftm_range_t, rtt_sigma_ns) }, \
         { "n_frames", NULL, MAVLINK_TYPE_UINT8_T, 0, 24, offsetof(mavlink_pnt_ftm_range_t, n_frames) }, \
         } \
}
#endif

/**
 * @brief Pack a pnt_ftm_range message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param bssid_hash  
 * @param range_m  
 * @param rtt_sigma_ns  
 * @param n_frames  
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_ftm_range_pack(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg,
                               uint64_t time_us, const uint8_t *bssid_hash, float range_m, float rtt_sigma_ns, uint8_t n_frames)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, range_m);
    _mav_put_float(buf, 12, rtt_sigma_ns);
    _mav_put_uint8_t(buf, 24, n_frames);
    _mav_put_uint8_t_array(buf, 16, bssid_hash, 8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN);
#else
    mavlink_pnt_ftm_range_t packet;
    packet.time_us = time_us;
    packet.range_m = range_m;
    packet.rtt_sigma_ns = rtt_sigma_ns;
    packet.n_frames = n_frames;
    mav_array_memcpy(packet.bssid_hash, bssid_hash, sizeof(uint8_t)*8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_FTM_RANGE;
    return mavlink_finalize_message(msg, system_id, component_id, MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_CRC);
}

/**
 * @brief Pack a pnt_ftm_range message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param bssid_hash  
 * @param range_m  
 * @param rtt_sigma_ns  
 * @param n_frames  
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_ftm_range_pack_status(uint8_t system_id, uint8_t component_id, mavlink_status_t *_status, mavlink_message_t* msg,
                               uint64_t time_us, const uint8_t *bssid_hash, float range_m, float rtt_sigma_ns, uint8_t n_frames)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, range_m);
    _mav_put_float(buf, 12, rtt_sigma_ns);
    _mav_put_uint8_t(buf, 24, n_frames);
    _mav_put_uint8_t_array(buf, 16, bssid_hash, 8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN);
#else
    mavlink_pnt_ftm_range_t packet;
    packet.time_us = time_us;
    packet.range_m = range_m;
    packet.rtt_sigma_ns = rtt_sigma_ns;
    packet.n_frames = n_frames;
    mav_array_memcpy(packet.bssid_hash, bssid_hash, sizeof(uint8_t)*8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_FTM_RANGE;
#if MAVLINK_CRC_EXTRA
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_CRC);
#else
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN);
#endif
}

/**
 * @brief Pack a pnt_ftm_range message on a channel
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param time_us  Hub monotonic time.
 * @param bssid_hash  
 * @param range_m  
 * @param rtt_sigma_ns  
 * @param n_frames  
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_ftm_range_pack_chan(uint8_t system_id, uint8_t component_id, uint8_t chan,
                               mavlink_message_t* msg,
                                   uint64_t time_us,const uint8_t *bssid_hash,float range_m,float rtt_sigma_ns,uint8_t n_frames)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, range_m);
    _mav_put_float(buf, 12, rtt_sigma_ns);
    _mav_put_uint8_t(buf, 24, n_frames);
    _mav_put_uint8_t_array(buf, 16, bssid_hash, 8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN);
#else
    mavlink_pnt_ftm_range_t packet;
    packet.time_us = time_us;
    packet.range_m = range_m;
    packet.rtt_sigma_ns = rtt_sigma_ns;
    packet.n_frames = n_frames;
    mav_array_memcpy(packet.bssid_hash, bssid_hash, sizeof(uint8_t)*8);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_FTM_RANGE;
    return mavlink_finalize_message_chan(msg, system_id, component_id, chan, MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_CRC);
}

/**
 * @brief Encode a pnt_ftm_range struct
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 * @param pnt_ftm_range C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_ftm_range_encode(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg, const mavlink_pnt_ftm_range_t* pnt_ftm_range)
{
    return mavlink_msg_pnt_ftm_range_pack(system_id, component_id, msg, pnt_ftm_range->time_us, pnt_ftm_range->bssid_hash, pnt_ftm_range->range_m, pnt_ftm_range->rtt_sigma_ns, pnt_ftm_range->n_frames);
}

/**
 * @brief Encode a pnt_ftm_range struct on a channel
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param pnt_ftm_range C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_ftm_range_encode_chan(uint8_t system_id, uint8_t component_id, uint8_t chan, mavlink_message_t* msg, const mavlink_pnt_ftm_range_t* pnt_ftm_range)
{
    return mavlink_msg_pnt_ftm_range_pack_chan(system_id, component_id, chan, msg, pnt_ftm_range->time_us, pnt_ftm_range->bssid_hash, pnt_ftm_range->range_m, pnt_ftm_range->rtt_sigma_ns, pnt_ftm_range->n_frames);
}

/**
 * @brief Encode a pnt_ftm_range struct with provided status structure
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 * @param pnt_ftm_range C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_ftm_range_encode_status(uint8_t system_id, uint8_t component_id, mavlink_status_t* _status, mavlink_message_t* msg, const mavlink_pnt_ftm_range_t* pnt_ftm_range)
{
    return mavlink_msg_pnt_ftm_range_pack_status(system_id, component_id, _status, msg,  pnt_ftm_range->time_us, pnt_ftm_range->bssid_hash, pnt_ftm_range->range_m, pnt_ftm_range->rtt_sigma_ns, pnt_ftm_range->n_frames);
}

/**
 * @brief Send a pnt_ftm_range message
 * @param chan MAVLink channel to send the message
 *
 * @param time_us  Hub monotonic time.
 * @param bssid_hash  
 * @param range_m  
 * @param rtt_sigma_ns  
 * @param n_frames  
 */
#ifdef MAVLINK_USE_CONVENIENCE_FUNCTIONS

static inline void mavlink_msg_pnt_ftm_range_send(mavlink_channel_t chan, uint64_t time_us, const uint8_t *bssid_hash, float range_m, float rtt_sigma_ns, uint8_t n_frames)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, range_m);
    _mav_put_float(buf, 12, rtt_sigma_ns);
    _mav_put_uint8_t(buf, 24, n_frames);
    _mav_put_uint8_t_array(buf, 16, bssid_hash, 8);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_FTM_RANGE, buf, MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_CRC);
#else
    mavlink_pnt_ftm_range_t packet;
    packet.time_us = time_us;
    packet.range_m = range_m;
    packet.rtt_sigma_ns = rtt_sigma_ns;
    packet.n_frames = n_frames;
    mav_array_memcpy(packet.bssid_hash, bssid_hash, sizeof(uint8_t)*8);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_FTM_RANGE, (const char *)&packet, MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_CRC);
#endif
}

/**
 * @brief Send a pnt_ftm_range message
 * @param chan MAVLink channel to send the message
 * @param struct The MAVLink struct to serialize
 */
static inline void mavlink_msg_pnt_ftm_range_send_struct(mavlink_channel_t chan, const mavlink_pnt_ftm_range_t* pnt_ftm_range)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    mavlink_msg_pnt_ftm_range_send(chan, pnt_ftm_range->time_us, pnt_ftm_range->bssid_hash, pnt_ftm_range->range_m, pnt_ftm_range->rtt_sigma_ns, pnt_ftm_range->n_frames);
#else
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_FTM_RANGE, (const char *)pnt_ftm_range, MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_CRC);
#endif
}

#if MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN <= MAVLINK_MAX_PAYLOAD_LEN
/*
  This variant of _send() can be used to save stack space by reusing
  memory from the receive buffer.  The caller provides a
  mavlink_message_t which is the size of a full mavlink message. This
  is usually the receive buffer for the channel, and allows a reply to an
  incoming message with minimum stack space usage.
 */
static inline void mavlink_msg_pnt_ftm_range_send_buf(mavlink_message_t *msgbuf, mavlink_channel_t chan,  uint64_t time_us, const uint8_t *bssid_hash, float range_m, float rtt_sigma_ns, uint8_t n_frames)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char *buf = (char *)msgbuf;
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, range_m);
    _mav_put_float(buf, 12, rtt_sigma_ns);
    _mav_put_uint8_t(buf, 24, n_frames);
    _mav_put_uint8_t_array(buf, 16, bssid_hash, 8);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_FTM_RANGE, buf, MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_CRC);
#else
    mavlink_pnt_ftm_range_t *packet = (mavlink_pnt_ftm_range_t *)msgbuf;
    packet->time_us = time_us;
    packet->range_m = range_m;
    packet->rtt_sigma_ns = rtt_sigma_ns;
    packet->n_frames = n_frames;
    mav_array_memcpy(packet->bssid_hash, bssid_hash, sizeof(uint8_t)*8);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_FTM_RANGE, (const char *)packet, MAVLINK_MSG_ID_PNT_FTM_RANGE_MIN_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN, MAVLINK_MSG_ID_PNT_FTM_RANGE_CRC);
#endif
}
#endif

#endif

// MESSAGE PNT_FTM_RANGE UNPACKING


/**
 * @brief Get field time_us from pnt_ftm_range message
 *
 * @return  Hub monotonic time.
 */
static inline uint64_t mavlink_msg_pnt_ftm_range_get_time_us(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint64_t(msg,  0);
}

/**
 * @brief Get field bssid_hash from pnt_ftm_range message
 *
 * @return  
 */
static inline uint16_t mavlink_msg_pnt_ftm_range_get_bssid_hash(const mavlink_message_t* msg, uint8_t *bssid_hash)
{
    return _MAV_RETURN_uint8_t_array(msg, bssid_hash, 8,  16);
}

/**
 * @brief Get field range_m from pnt_ftm_range message
 *
 * @return  
 */
static inline float mavlink_msg_pnt_ftm_range_get_range_m(const mavlink_message_t* msg)
{
    return _MAV_RETURN_float(msg,  8);
}

/**
 * @brief Get field rtt_sigma_ns from pnt_ftm_range message
 *
 * @return  
 */
static inline float mavlink_msg_pnt_ftm_range_get_rtt_sigma_ns(const mavlink_message_t* msg)
{
    return _MAV_RETURN_float(msg,  12);
}

/**
 * @brief Get field n_frames from pnt_ftm_range message
 *
 * @return  
 */
static inline uint8_t mavlink_msg_pnt_ftm_range_get_n_frames(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint8_t(msg,  24);
}

/**
 * @brief Decode a pnt_ftm_range message into a struct
 *
 * @param msg The message to decode
 * @param pnt_ftm_range C-struct to decode the message contents into
 */
static inline void mavlink_msg_pnt_ftm_range_decode(const mavlink_message_t* msg, mavlink_pnt_ftm_range_t* pnt_ftm_range)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    pnt_ftm_range->time_us = mavlink_msg_pnt_ftm_range_get_time_us(msg);
    pnt_ftm_range->range_m = mavlink_msg_pnt_ftm_range_get_range_m(msg);
    pnt_ftm_range->rtt_sigma_ns = mavlink_msg_pnt_ftm_range_get_rtt_sigma_ns(msg);
    mavlink_msg_pnt_ftm_range_get_bssid_hash(msg, pnt_ftm_range->bssid_hash);
    pnt_ftm_range->n_frames = mavlink_msg_pnt_ftm_range_get_n_frames(msg);
#else
        uint8_t len = msg->len < MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN? msg->len : MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN;
        memset(pnt_ftm_range, 0, MAVLINK_MSG_ID_PNT_FTM_RANGE_LEN);
    memcpy(pnt_ftm_range, _MAV_PAYLOAD(msg), len);
#endif
}
